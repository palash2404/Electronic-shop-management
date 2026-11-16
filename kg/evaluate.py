"""Measure the model instead of guessing: the same inputs, scored the same way, every run.

  .venv/bin/python -m kg.evaluate extraction   # 5 datasheets against data/datasheets/gold.json
  .venv/bin/python -m kg.evaluate questions    # 10 questions against answers computed with Cypher
  .venv/bin/python -m kg.evaluate questions --limit 3

Both print a score table and save it under eval/results/, so two models or two
versions of a prompt can be compared.

The runs go through Langfuse's experiment runner. With LANGFUSE keys in .env each
run also shows up in Langfuse with its traces and scores. Without keys it runs
locally and nothing is sent anywhere.

The scoring itself is plain code (no model judges a model):
  extraction  compare with a hand-written answer key, material by material
  questions   run a hand-written Cypher query for the true answer, then check
              that the reply contains it and names nothing it should not
"""
import asyncio
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from statistics import mean

from kg.extract import Plan, extractor, make_plan, read_sheet, settings
from kg.query import table

ROOT = Path(__file__).resolve().parent.parent
SHEETS = ROOT / "data" / "datasheets"
QUESTIONS = ROOT / "eval" / "questions.json"
RESULTS = ROOT / "eval" / "results"

EXTRACTION_METRICS = ["fields", "precision", "recall", "f1", "mass", "hazard"]


# ---------- scoring: datasheet extraction ----------

def same_name(a: str, b: str) -> bool:
    """True if one name contains the other, ignoring case and punctuation."""
    a, b = (re.sub(r"[^a-z0-9]+", " ", x.lower()).strip() for x in (a, b))
    return bool(a) and bool(b) and (a in b or b in a)


def plan_output(plan: Plan) -> dict:
    return {"component_name": plan.name, "component_type": plan.component_type,
            "manufacturer": plan.manufacturer, "recyclable": plan.recyclable,
            "materials": [{"name": x.name, "cas": x.cas, "mass_g": x.mass_g,
                           "hazard": x.hazard_note is not None} for x in plan.lines],
            "problems": plan.problems}


def score_extraction(output: dict, gold: dict) -> dict[str, float]:
    """Compare one extracted datasheet with its answer key. Every score is 0..1.

    fields     share of the four component fields that are right
    precision  share of the extracted materials that are really in the sheet
    recall     share of the sheet's materials that were extracted
    f1         the two combined
    mass       share of the matched materials whose grams are right (within 2 %)
    hazard     share of the matched materials with the right hazard flag
    """
    if "error" in output:
        return dict.fromkeys(EXTRACTION_METRICS, 0.0)

    fields = mean([same_name(output["component_name"], gold["component_name"]),
                   output["component_type"] == gold["component_type"],
                   same_name(output["manufacturer"], gold["manufacturer"]),
                   output["recyclable"] == gold["recyclable"]])

    # A material is identified by its CAS number, or by its name if it has none.
    def key(m: dict) -> str:
        return m["cas"] or m["name"].lower()

    want = {key(m): m for m in gold["materials"]}
    got = {key(m): m for m in output["materials"]}
    hit = want.keys() & got.keys()
    precision = len(hit) / len(got) if got else 0.0
    recall = len(hit) / len(want)
    f1 = 2 * precision * recall / (precision + recall) if hit else 0.0
    mass = mean(abs(got[k]["mass_g"] - want[k]["mass_g"]) <= max(0.02 * want[k]["mass_g"], 0.001)
                for k in hit) if hit else 0.0
    hazard = mean(got[k]["hazard"] == (k in gold["hazardous"]) for k in hit) if hit else 0.0
    return {"fields": fields, "precision": precision, "recall": recall,
            "f1": f1, "mass": mass, "hazard": hazard}


# ---------- scoring: questions ----------

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def score_answer(answer: str, expected: list, universe: list[str]) -> tuple[bool, str]:
    """Is the reply right? It must contain every expected value, and it must not
    name any other candidate (universe: all names of that kind, e.g. all products)."""
    text = answer.lower()
    numbers = [float(n.replace(",", "")) for n in NUMBER.findall(answer)]

    # Which names does the reply mention? Longest first, and each match is removed,
    # so "Pulse 6" is not found inside "Pulse 6 Lite".
    mentioned = set()
    for name in sorted({*universe, *(v for v in expected if isinstance(v, str))}, key=len, reverse=True):
        if name.lower() in text:
            mentioned.add(name)
            text = text.replace(name.lower(), " ")

    missing = [str(v) for v in expected
               if (not any(abs(n - v) < 0.005 for n in numbers) if isinstance(v, (int, float))
                   else v not in mentioned)]
    extra = [name for name in universe if name in mentioned and name not in expected]
    comment = "; ".join(part for part in (f"missing: {', '.join(missing)}" if missing else "",
                                          f"wrong extra: {', '.join(extra)}" if extra else "") if part)
    return not missing and not extra, comment


def true_answers(questions: list[dict]) -> list[dict]:
    """Run each question's Cypher to get the answer the reply is checked against."""
    from kg.to_neo4j import driver

    def values(db, cypher: str) -> list:
        return [v for record in db.execute_query(cypher).records for v in record.values()]

    with driver() as db:
        return [{"input": q["question"],
                 "expected_output": {"values": values(db, q["cypher"]),
                                     "universe": values(db, q["universe"]) if "universe" in q else []}}
                for q in questions]


# ---------- the two experiments ----------

async def patiently(call, waits: int = 5):
    """Run a model call; when the provider says 'rate limit', wait a minute and try again."""
    from pydantic_ai.exceptions import ModelHTTPError
    for attempt in range(waits + 1):
        start = time.time()
        try:
            return await call(), round(time.time() - start)
        except ModelHTTPError as e:
            if e.status_code != 429 or attempt == waits:
                raise
            await asyncio.sleep(62)

def run_extraction(model: str, limit: int | None) -> tuple[list[str], list[list], dict]:
    from langfuse import Evaluation, get_client

    gold = json.loads((SHEETS / "gold.json").read_text())
    data = [{"input": {"file": name, "text": read_sheet(SHEETS / name)}, "expected_output": answer}
            for name, answer in list(gold.items())[:limit]]

    async def task(*, item, **_):
        start = time.time()
        try:
            sheet = (await extractor.run(item["input"]["text"], model=model,
                                         model_settings=settings(model))).output
            output = plan_output(make_plan(sheet))
        except Exception as e:          # the model gave up, or the server is down
            output = {"error": f"{type(e).__name__}: {e}"}
        return output | {"seconds": round(time.time() - start)}

    def evaluator(*, output, expected_output, **_):
        return [Evaluation(name=k, value=v) for k, v in score_extraction(output, expected_output).items()]

    result = get_client().run_experiment(name="datasheet-extraction", run_name=f"{model} {date.today()}",
                                         data=data, task=task, evaluators=[evaluator], max_concurrency=1)
    rows, items = [], []
    for r in result.item_results:
        scores = {e.name: e.value for e in r.evaluations}
        note = r.output.get("error") or "; ".join(r.output["problems"])
        rows.append([r.item["input"]["file"], *(f"{scores[m]:.2f}" for m in EXTRACTION_METRICS),
                     f"{r.output['seconds']}s", note[:60]])
        items.append({"file": r.item["input"]["file"], "scores": scores, "output": r.output})
    summary = {m: round(mean(i["scores"][m] for i in items), 3) for m in EXTRACTION_METRICS}
    rows.append(["MEAN", *(f"{summary[m]:.2f}" for m in EXTRACTION_METRICS), "", ""])
    return ["datasheet", *EXTRACTION_METRICS, "time", "note"], rows, {"summary": summary, "items": items}


def run_questions(model: str, limit: int | None) -> tuple[list[str], list[list], dict]:
    from langfuse import Evaluation, get_client
    from kg.agent import Deps, agent, run_settings

    data = true_answers(json.loads(QUESTIONS.read_text())[:limit])

    async def task(*, item, **_):
        try:    # confirm always says no: an evaluation must never change the data
            result, seconds = await patiently(lambda: agent.run(
                item["input"], model=model, deps=Deps(confirm=lambda _: False), model_settings=run_settings()))
            return {"answer": result.output, "seconds": seconds}
        except Exception as e:
            return {"answer": f"ERROR: {type(e).__name__}: {e}", "seconds": 0}

    def evaluator(*, output, expected_output, **_):
        correct, comment = score_answer(output["answer"], expected_output["values"], expected_output["universe"])
        return Evaluation(name="correct", value=float(correct), comment=comment)

    result = get_client().run_experiment(name="shop-questions", run_name=f"{model} {date.today()}",
                                         data=data, task=task, evaluators=[evaluator], max_concurrency=1)
    rows, items = [], []
    for n, r in enumerate(result.item_results, start=1):
        verdict = r.evaluations[0]
        rows.append([str(n), r.item["input"][:58], "yes" if verdict.value else "NO",
                     f"{r.output['seconds']}s", (verdict.comment or "")[:50]])
        items.append({"question": r.item["input"], "expected": r.item["expected_output"]["values"],
                      "correct": bool(verdict.value), "comment": verdict.comment, **r.output})
    right = sum(i["correct"] for i in items)
    rows.append(["", "TOTAL", f"{right}/{len(items)}", "", ""])
    return ["#", "question", "correct", "time", "why not"], rows, \
        {"summary": {"correct": right, "of": len(items)}, "items": items}


def main() -> None:
    from dotenv import load_dotenv
    from kg.agent import DEFAULT_MODEL, setup_tracing
    load_dotenv()
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    model = os.environ.get("ESHOP_MODEL", DEFAULT_MODEL)

    args = sys.argv[1:]
    kind = args[0] if args else ""
    if kind not in ("extraction", "questions"):
        sys.exit("Usage: python -m kg.evaluate extraction|questions [--limit N]")
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None

    tracing = setup_tracing()
    if not tracing:      # without keys the Langfuse client only complains that it is off
        import logging
        logging.getLogger("langfuse").setLevel(logging.CRITICAL)
    thinking = kind == "questions" or "extra_body" not in settings(model)
    print(f"Evaluating {kind} with {model} (thinking {'on' if thinking else 'off'}, "
          f"Langfuse {'on' if tracing else 'off'}) ...")
    cols, rows, details = (run_extraction if kind == "extraction" else run_questions)(model, limit)
    print()
    table(cols, rows)

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{kind}__{re.sub(r'[^A-Za-z0-9.-]+', '_', model)}{'__thinking' if thinking and kind == 'extraction' else ''}.json"
    out.write_text(json.dumps({"kind": kind, "model": model, "thinking": thinking,
                               "date": str(date.today()), **details},
                              indent=2, ensure_ascii=False) + "\n")
    print(f"\nSaved to {out.relative_to(ROOT)}")
    if tracing:
        from langfuse import get_client
        get_client().flush()


if __name__ == "__main__":
    main()
