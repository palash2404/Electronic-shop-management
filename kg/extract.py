"""Read a component datasheet and turn it into rows for the knowledge graph.

  .venv/bin/python -m kg.extract data/datasheets/ds01_gan_power_pcb.txt          # show what was read
  .venv/bin/python -m kg.extract data/datasheets/ds01_gan_power_pcb.txt --save   # and import it

The work is split in two:

  1. The model reads. It fills in a fixed form (the Datasheet class) with what
     the sheet says, as printed: names, CAS numbers, amounts and their units.
  2. Code does everything that can be computed: unit conversion, percent to
     grams, the CAS check digit, matching against the materials already known.

An import goes through kg/store.py, so it is validated with SHACL before
anything is saved, exactly like a change made by the assistant.
"""
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, NativeOutput

from db import query
from kg.store import Rejected, checked_write

ComponentType = Literal["battery", "display", "pcb", "casing", "glass", "audio",
                        "cable", "power", "electronic", "mechanical", "sensor"]

INSTRUCTIONS = """\
You read datasheets and safety data sheets for electronic components and fill in a form.

Rules:
- Copy what the sheet states. Do not add substances from your own knowledge.
- Leave out any substance the sheet says is absent, not added or not detected.
- amount and unit: copy the number as printed and choose the unit it is printed in
  (g, mg, or percent for "% by weight"). Do not convert between units.
- Write numbers with a decimal point: a German "1,45 g" is 1.45.
- cas_number: exactly as printed. Use null if the sheet gives none.
- Substance names in English (Kupfer -> Copper, Eisen -> Iron).
- hazard_note: the restriction or hazard classification the sheet states for that
  substance (for example "RoHS 2011/65/EU" or "CLP Carc. 2, H351"). Use null if the
  sheet states none or says "not classified".
- manufacturer: the company name only, without legal form or address
  ("CellCore Co., Ltd., Shenzhen" -> "CellCore").
- component_name: what the part is called, as on a parts list, for example
  "Li-ion pouch cell 4500 mAh". Not a part number, not a document number and
  not one of its materials.
- component_type: pcb for printed circuit boards and mainboards; battery for cells
  and packs; display for screens and panels; audio for speakers and microphones;
  power for chargers and power supplies; cable for cables and connectors; casing
  for housings; otherwise glass, sensor, mechanical or electronic.
"""


class Substance(BaseModel):
    name: str = Field(description="Substance name in English")
    cas_number: str | None = Field(description="CAS number as printed, or null")
    amount: float = Field(description="The number as printed")
    unit: Literal["g", "mg", "percent"] = Field(description="The unit the amount is printed in")
    hazard_note: str | None = Field(default=None, description="Stated restriction or hazard class, or null")


class Datasheet(BaseModel):
    """What one datasheet says about one component."""
    component_name: str = Field(description="What the part is called, not a part or document number")
    component_type: ComponentType
    manufacturer: str = Field(description="Company name only")
    recyclable: bool
    total_mass_g: float | None = Field(description="Mass of the whole component in grams, or null")
    substances: list[Substance]


# NativeOutput asks the model server for JSON that fits the schema. With Ollama the
# output is constrained while it is generated, so even a small model returns a valid form.
extractor = Agent(output_type=NativeOutput(Datasheet), instructions=INSTRUCTIONS)


def read_sheet(path: Path) -> str:
    """The text of a datasheet. PDFs are read with pypdf."""
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    return path.read_text(encoding="utf-8")


def settings(model) -> dict:
    """Request settings for form filling.

    Temperature 0: the same sheet should give the same form every time.
    Thinking off for Ollama models: Qwen3 writes out its reasoning before it answers,
    which made a sheet five to ten times slower and no more accurate (kg/evaluate.py).
    ESHOP_THINK=1 turns it back on. The assistant in kg/agent.py keeps thinking on:
    with it off, the model put its reasoning into the answers and was no faster.
    """
    if str(model).startswith("ollama:") and os.environ.get("ESHOP_THINK") != "1":
        return {"temperature": 0, "extra_body": {"reasoning_effort": "none"}}
    return {"temperature": 0}


def extract(text: str, model: str) -> Datasheet:
    return extractor.run_sync(text, model=model, model_settings=settings(model)).output


# ---------- from here on: plain code, no model ----------

CAS = re.compile(r"^(\d{2,7})-(\d{2})-(\d)$")
# A model sometimes copies "not classified" into the hazard note instead of leaving it empty.
NO_HAZARD = re.compile(r"^\W*(not classified|not hazardous|non-hazardous|none|no|n/?a|nicht eingestuft)?\W*$", re.I)


def cas_ok(cas: str) -> bool:
    """A CAS number carries a check digit: the last digit must equal the weighted
    sum of the others modulo 10. This catches most misread or invented numbers."""
    m = CAS.match(cas)
    if not m:
        return False
    digits = (m.group(1) + m.group(2))[::-1]
    return sum(int(d) * i for i, d in enumerate(digits, start=1)) % 10 == int(m.group(3))


@dataclass
class Line:
    name: str
    cas: str | None
    mass_g: float
    material_id: str | None = None     # None: not in the database yet
    hazard_note: str | None = None


@dataclass
class Plan:
    """A datasheet after the checks: what would be written, and what is wrong."""
    name: str
    component_type: str
    manufacturer: str
    manufacturer_id: str | None
    recyclable: bool
    lines: list[Line] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)   # these block an import
    notes: list[str] = field(default_factory=list)      # these do not


def make_plan(sheet: Datasheet, fetch=query) -> Plan:
    """Convert units, check CAS numbers and match against what the database knows."""
    makers = {r["name"].lower(): r["manufacturer_id"] for r in fetch("SELECT * FROM manufacturer")}
    materials = fetch("SELECT * FROM material")
    by_cas = {r["cas_number"]: r for r in materials if r["cas_number"]}
    by_name = {r["name"].lower(): r for r in materials}

    stated = sheet.manufacturer.strip()
    # "CellCore Co., Ltd." should still find CellCore: the longest known name inside the stated one.
    maker = max((n for n in makers if n in stated.lower()), key=len, default=None)
    plan = Plan(sheet.component_name.strip(), sheet.component_type, stated,
                makers.get(maker), sheet.recyclable)
    if plan.manufacturer_id is None:
        plan.notes.append(f"Manufacturer '{plan.manufacturer}' is not in the database; it will be left empty.")
    if not sheet.substances:
        plan.problems.append("No substances were found.")

    for s in sheet.substances:
        name = s.name.strip()
        cas = s.cas_number.strip() if s.cas_number and s.cas_number.strip() not in ("", "-") else None
        if cas and not cas_ok(cas):
            plan.problems.append(f"{name}: CAS number '{cas}' fails the check digit test.")
            continue

        if s.unit == "g":
            mass = s.amount
        elif s.unit == "mg":
            mass = s.amount / 1000
        elif sheet.total_mass_g:
            mass = s.amount / 100 * sheet.total_mass_g
        else:
            plan.problems.append(f"{name}: given in percent, but the sheet states no total mass.")
            continue
        if s.amount == 0:             # "n.d." or "0" read as a number: the substance is absent
            plan.notes.append(f"{name}: listed with amount 0, left out.")
            continue
        mass = round(mass, 3)
        if mass <= 0:
            plan.problems.append(f"{name}: mass must be above 0 g (read {s.amount} {s.unit}).")
            continue

        known = by_cas.get(cas) if cas else by_name.get(name.lower())
        hazard = s.hazard_note if s.hazard_note and not NO_HAZARD.match(s.hazard_note) else None
        line = Line(known["name"] if known else name, cas, mass,
                    known["material_id"] if known else None, hazard)
        same = next((x for x in plan.lines if (x.cas, x.name.lower()) == (line.cas, line.name.lower())), None)
        if same:                      # listed twice, e.g. copper in two sub-parts
            same.mass_g = round(same.mass_g + mass, 3)
        else:
            plan.lines.append(line)
    return plan


def _next_id(prefix: str, taken: list[str], offset: int = 0) -> str:
    numbers = [int(t[len(prefix):]) for t in taken if t[len(prefix):].isdigit()]
    return f"{prefix}{max(numbers, default=0) + 1 + offset:02d}"


def statements(plan: Plan, fetch=query) -> tuple[str, list[tuple[str, tuple]]]:
    """The SQL for a plan, with a one-paragraph summary for the confirmation prompt."""
    component_id = _next_id("C", [r["component_id"] for r in fetch("SELECT component_id FROM component")])
    material_ids = [r["material_id"] for r in fetch("SELECT material_id FROM material")]

    sql = [("INSERT INTO component (component_id, name, component_type, manufacturer_id, recyclable)"
            " VALUES (?, ?, ?, ?, ?)",
            (component_id, plan.name, plan.component_type, plan.manufacturer_id, plan.recyclable))]
    new = 0
    for line in plan.lines:
        material_id = line.material_id
        if material_id is None:
            material_id = _next_id("M", material_ids, offset=new)
            new += 1
            sql.append(("INSERT INTO material (material_id, name, cas_number, is_hazardous, regulation)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (material_id, line.name, line.cas, line.hazard_note is not None, line.hazard_note)))
        sql.append(("INSERT INTO component_material (component_id, material_id, mass_g) VALUES (?, ?, ?)",
                    (component_id, material_id, line.mass_g)))
    summary = (f"Add component {component_id} '{plan.name}' ({plan.component_type}) with "
               f"{len(plan.lines)} materials, {new} of them new")
    return summary, sql


def show(plan: Plan) -> None:
    print(f"\n{plan.name}")
    print(f"  type {plan.component_type} | manufacturer {plan.manufacturer}"
          f" ({plan.manufacturer_id or 'unknown'}) | recyclable {'yes' if plan.recyclable else 'no'}")
    for line in plan.lines:
        where = line.material_id or "NEW"
        hazard = f"   [{line.hazard_note}]" if line.hazard_note else ""
        print(f"  {where:4} {line.name:30} {line.cas or '-':12} {line.mass_g:>9.3f} g{hazard}")
    for text in plan.notes:
        print(f"  note: {text}")
    for text in plan.problems:
        print(f"  PROBLEM: {text}")


def main() -> None:
    from dotenv import load_dotenv
    from kg.agent import DEFAULT_MODEL
    load_dotenv()
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    model = os.environ.get("ESHOP_MODEL", DEFAULT_MODEL)

    paths = [Path(a) for a in sys.argv[1:] if a != "--save"]
    if not paths:
        sys.exit("Usage: python -m kg.extract <datasheet.txt|.pdf> [--save]")
    for path in paths:
        print(f"Reading {path.name} with {model} ...")
        plan = make_plan(extract(read_sheet(path), model))
        show(plan)
        if "--save" not in sys.argv:
            continue
        if plan.problems:
            print("  Not saved: fix the problems above first.")
            continue
        summary, sql = statements(plan)
        if input(f"\n  {summary}\n  Apply? [y/N] ").strip().lower() != "y":
            print("  Not saved.")
            continue
        try:
            print(" ", checked_write(sql))
        except Rejected as e:
            print("  REJECTED, nothing was changed:\n  - " + "\n  - ".join(e.reasons))


if __name__ == "__main__":
    main()
