"""Tests for datasheet extraction and for the scoring code. No model needed.

The model's part is a filled-in Datasheet form. These tests start from such a
form and check everything the code does with it: units, CAS check digits,
matching, the SHACL-checked import, and the scores.
"""
import json

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

import db
import kg.store
from kg.evaluate import SHEETS, score_answer, score_extraction
from kg.extract import Datasheet, Line, Plan, Substance, cas_ok, extractor, make_plan, statements
from kg.store import Rejected, checked_write


def sheet(*substances: Substance, total_mass_g: float | None = None, **overrides) -> Datasheet:
    base = dict(component_name="Test cell", component_type="battery", manufacturer="CellCore",
                recyclable=True, total_mass_g=total_mass_g, substances=list(substances))
    return Datasheet(**(base | overrides))


COPPER = Substance(name="Copper", cas_number="7440-50-8", amount=7.2, unit="g")


# ---------- CAS numbers ----------

@pytest.mark.parametrize("cas", ["7440-50-8", "96-49-1", "21324-40-3", "65997-17-3"])
def test_real_cas_numbers_pass(cas):
    assert cas_ok(cas)


@pytest.mark.parametrize("cas", ["7440-50-9", "7440-05-8", "744-050-8", "copper", ""])
def test_wrong_cas_numbers_fail(cas):
    assert not cas_ok(cas)


def test_a_misread_cas_number_blocks_the_import():
    plan = make_plan(sheet(COPPER, Substance(name="Tin", cas_number="7440-31-6", amount=1, unit="g")))
    assert [x.name for x in plan.lines] == ["Copper"]
    assert "check digit" in plan.problems[0]


# ---------- units and matching ----------

def test_units_are_converted_to_grams_in_code():
    plan = make_plan(sheet(
        COPPER,
        Substance(name="Gold", cas_number="7440-57-5", amount=3, unit="mg"),
        Substance(name="Graphite", cas_number="7782-42-5", amount=16.5, unit="percent"),
        total_mass_g=86.0))
    assert {x.name: x.mass_g for x in plan.lines} == {"Copper": 7.2, "Gold": 0.003, "Graphite": 14.19}
    assert not plan.problems


def test_percent_without_a_total_mass_is_a_problem():
    plan = make_plan(sheet(Substance(name="Graphite", cas_number="7782-42-5", amount=16.5, unit="percent")))
    assert not plan.lines and "no total mass" in plan.problems[0]


def test_materials_are_matched_by_cas_number_not_by_spelling():
    plan = make_plan(sheet(
        Substance(name="Kupfer", cas_number="7440-50-8", amount=1, unit="g"),        # known, other name
        Substance(name="Aluminosilicate glass", cas_number=None, amount=14.2, unit="g"),  # known, no CAS
        Substance(name="Iron", cas_number="7439-89-6", amount=3.1, unit="g")))       # not in the database
    assert [(x.name, x.material_id) for x in plan.lines] == [
        ("Copper", "M04"), ("Aluminosilicate glass", "M19"), ("Iron", None)]


def test_manufacturer_is_found_despite_legal_form_and_address():
    assert make_plan(sheet(COPPER, manufacturer="CellCore Co., Ltd.")).manufacturer_id == "MF06"


def test_a_substance_read_with_amount_zero_is_left_out():
    plan = make_plan(sheet(COPPER, Substance(name="Mercury", cas_number="7439-97-6", amount=0, unit="g")))
    assert [x.name for x in plan.lines] == ["Copper"]
    assert not plan.problems and "left out" in plan.notes[0]


@pytest.mark.parametrize("note, hazardous", [("not classified", False), ("None", False), ("-", False),
                                             ("CLP Carc. 2, H351", True), ("RoHS 2011/65/EU", True)])
def test_not_classified_is_not_a_hazard(note, hazardous):
    plan = make_plan(sheet(Substance(name="Copper", cas_number="7440-50-8", amount=1, unit="g", hazard_note=note)))
    assert (plan.lines[0].hazard_note is not None) == hazardous


def test_unknown_manufacturer_is_a_note_not_a_problem():
    plan = make_plan(sheet(COPPER, manufacturer="Nobody Ltd"))
    assert plan.manufacturer_id is None and plan.notes and not plan.problems


# ---------- import through the SHACL-checked write ----------

def test_import_adds_the_component_and_its_new_materials():
    plan = make_plan(sheet(
        COPPER,
        Substance(name="Lithium hexafluorophosphate", cas_number="21324-40-3", amount=2.0, unit="percent",
                  hazard_note="CLP Acute Tox. 3, H301"),
        total_mass_g=86.0))
    summary, sql = statements(plan)
    assert "C28" in summary and "1 of them new" in summary
    assert checked_write(sql).startswith("Saved")

    assert db.query("SELECT name FROM component WHERE component_id = 'C28'")[0]["name"] == "Test cell"
    new = db.query("SELECT * FROM material WHERE material_id = 'M22'")[0]
    assert (new["cas_number"], bool(new["is_hazardous"])) == ("21324-40-3", True)
    assert "21324-40-3" in kg.store.DATA_PATH.read_text()


def test_shacl_still_rejects_what_slips_past_the_code_checks():
    # Build a plan by hand with a malformed CAS number, as if the check above were missing.
    plan = Plan("Bad part", "pcb", "CellCore", "MF06", True, lines=[Line("Mystery", "not-a-cas", 1.0)])
    with pytest.raises(Rejected) as e:
        checked_write(statements(plan)[1])
    assert any("CAS" in reason for reason in e.value.reasons)
    assert not db.query("SELECT 1 FROM component WHERE name = 'Bad part'")


# ---------- the model's part, played by a fake model ----------

def test_extractor_turns_the_model_reply_into_a_datasheet():
    reply = sheet(COPPER).model_dump_json()
    fake = FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart(reply)]))
    result = extractor.run_sync("any datasheet text", model=fake).output
    assert result.substances[0].cas_number == "7440-50-8"


# ---------- scoring ----------

GOLD = {"component_name": "Test cell", "component_type": "battery", "manufacturer": "CellCore",
        "recyclable": True, "hazardous": ["7439-92-1"],
        "materials": [{"name": "Copper", "cas": "7440-50-8", "mass_g": 7.2},
                      {"name": "Lead", "cas": "7439-92-1", "mass_g": 0.54}]}


def output(**overrides) -> dict:
    base = {"component_name": "Test cell", "component_type": "battery", "manufacturer": "CellCore",
            "recyclable": True, "problems": [],
            "materials": [{"name": "Copper", "cas": "7440-50-8", "mass_g": 7.2, "hazard": False},
                          {"name": "Lead", "cas": "7439-92-1", "mass_g": 0.54, "hazard": True}]}
    return base | overrides


def test_a_perfect_extraction_scores_one_everywhere():
    assert set(score_extraction(output(), GOLD).values()) == {1.0}


def test_missed_and_invented_materials_lower_recall_and_precision():
    materials = [{"name": "Copper", "cas": "7440-50-8", "mass_g": 72.0, "hazard": False},   # mass wrong
                 {"name": "Mercury", "cas": "7439-97-6", "mass_g": 0.1, "hazard": True}]    # not in the sheet
    scores = score_extraction(output(materials=materials, recyclable=False), GOLD)
    assert scores == {"fields": 0.75, "precision": 0.5, "recall": 0.5, "f1": 0.5, "mass": 0.0, "hazard": 1.0}


def test_a_failed_extraction_scores_zero():
    assert set(score_extraction({"error": "timeout"}, GOLD).values()) == {0.0}


PRODUCTS = ["Voltaris Pulse 6", "Voltaris Pulse 6 Lite", "Kestrel K3"]


def test_answer_with_all_expected_values_is_correct():
    assert score_answer("They are the **Voltaris Pulse 6 Lite** and the Kestrel K3.",
                        ["Voltaris Pulse 6 Lite", "Kestrel K3"], PRODUCTS) == (True, "")


def test_answer_missing_a_value_or_naming_a_wrong_one_is_not_correct():
    assert score_answer("Only the Kestrel K3.", ["Voltaris Pulse 6", "Kestrel K3"], PRODUCTS)[1] \
        == "missing: Voltaris Pulse 6"
    assert score_answer("Kestrel K3 and Voltaris Pulse 6 Lite.", ["Kestrel K3"], PRODUCTS)[1] \
        == "wrong extra: Voltaris Pulse 6 Lite"


def test_a_longer_name_does_not_count_as_the_shorter_one():
    assert score_answer("The Voltaris Pulse 6 Lite.", ["Voltaris Pulse 6"], PRODUCTS) \
        == (False, "missing: Voltaris Pulse 6; wrong extra: Voltaris Pulse 6 Lite")


def test_numbers_are_compared_as_numbers():
    assert score_answer("Revenue was €2,325.00 in total.", [2325.0], [])[0]
    assert score_answer("There are 20 products.", [20], [])[0]
    assert not score_answer("There are 21 products.", [20], [])[0]


# ---------- the answer key itself ----------

def test_answer_key_matches_the_datasheet_files():
    gold = json.loads((SHEETS / "gold.json").read_text())
    assert sorted(gold) == sorted(p.name for p in SHEETS.glob("*.txt"))
    for name, answer in gold.items():
        text = (SHEETS / name).read_text()
        for m in answer["materials"]:
            if m["cas"]:
                assert cas_ok(m["cas"]) and m["cas"] in text, (name, m)


# ---------- the whole extraction experiment, with a fake model that reads perfectly ----------

def test_extraction_experiment_scores_a_perfect_reader_with_one():
    from pydantic_ai.messages import UserPromptPart
    from kg.evaluate import run_extraction

    gold = json.loads((SHEETS / "gold.json").read_text())
    by_text = {(SHEETS / name).read_text(): answer for name, answer in gold.items()}

    def respond(messages, info):
        text = next(p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        g = by_text[text]
        return ModelResponse(parts=[TextPart(Datasheet(
            component_name=g["component_name"], component_type=g["component_type"],
            manufacturer=g["manufacturer"], recyclable=g["recyclable"], total_mass_g=None,
            substances=[Substance(name=m["name"], cas_number=m["cas"], amount=m["mass_g"], unit="g",
                                  hazard_note="stated" if m["cas"] in g["hazardous"] else None)
                        for m in g["materials"]]).model_dump_json())])

    cols, rows, details = run_extraction(FunctionModel(respond), limit=None)
    assert len(details["items"]) == 5
    assert set(details["summary"].values()) == {1.0}
