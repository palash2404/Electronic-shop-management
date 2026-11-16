"""Tests for the agent's tools and its safety gates. No API key needed.

  .venv/bin/python -m pytest -q

Instead of a real model, each test uses a FunctionModel: a small function that
plays the model's part and decides which tool to call. That makes the test
repeatable, and it checks the part that matters for safety, which is what
happens to the data whatever the model asks for.

Every test runs on a temporary copy of the database. Neo4j is not touched.
"""
import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

import db
import kg.store
from kg.agent import Deps, agent, query_graph

YES = Deps(confirm=lambda summary: True)
NO = Deps(confirm=lambda summary: False)


@pytest.fixture(autouse=True)
def temp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "eshop.db")
    monkeypatch.setattr(kg.store, "DATA_PATH", tmp_path / "data.ttl")
    monkeypatch.setattr(kg.store, "sync_neo4j", lambda graph: "Neo4j skipped in tests.")
    db.init_db()


def scripted(tool_name: str, args: dict) -> FunctionModel:
    """A fake model: first it calls one tool, then it repeats the tool's answer."""
    def respond(messages, info):
        returns = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        if not returns:
            return ModelResponse(parts=[ToolCallPart(tool_name, args)])
        return ModelResponse(parts=[TextPart(str(returns[-1].content))])
    return FunctionModel(respond)


def run(tool_name: str, args: dict, deps: Deps = YES) -> str:
    return agent.run_sync("test", model=scripted(tool_name, args), deps=deps).output


def product(pid: str) -> dict | None:
    rows = db.query("SELECT * FROM product WHERE product_id = ?", (pid,))
    return rows[0] if rows else None


def new_product(**overrides) -> dict:
    base = dict(product_id="P21", name="Test Phone", category="Smartphone", manufacturer_id="MF01",
                unit_price=199.0, stock_qty=5, release_year=2026, condition="new",
                parts=[{"component_id": "C02", "quantity": 1}, {"component_id": "C12", "quantity": 1}])
    return {"product": base | overrides}


def test_valid_product_is_saved_and_reaches_the_rdf_graph(tmp_path):
    assert run("add_product", new_product()).startswith("Saved")
    assert product("P21")["name"] == "Test Phone"
    assert "ex:P21" in (tmp_path / "data.ttl").read_text()


def test_declined_change_is_not_saved():
    assert "DECLINED" in run("update_product", {"product_id": "P01", "unit_price": 1.0}, deps=NO)
    assert product("P01")["unit_price"] == 599


def test_shacl_rejects_new_product_with_rohs_material():
    # C15 is a leaded board. SQL has no rule against this; the SHACL shape does.
    out = run("add_product", new_product(parts=[{"component_id": "C15", "quantity": 1}]))
    assert "REJECTED" in out and "RoHS" in out
    assert product("P21") is None


def test_same_product_is_allowed_as_refurbished():
    out = run("add_product", new_product(condition="refurbished",
                                         parts=[{"component_id": "C15", "quantity": 1}]))
    assert out.startswith("Saved")


def test_shacl_rejects_product_without_parts():
    out = run("add_product", new_product(parts=[]))
    assert "REJECTED" in out and "at least one component" in out
    assert product("P21") is None


def test_database_rejects_unknown_manufacturer():
    out = run("add_product", new_product(manufacturer_id="MF99"))
    assert "REJECTED" in out and "FOREIGN KEY" in out
    assert product("P21") is None


def test_update_changes_price():
    assert run("update_product", {"product_id": "P01", "unit_price": 579.0}).startswith("Saved")
    assert product("P01")["unit_price"] == 579


def test_update_of_unknown_product_is_rejected():
    assert "Nothing matched" in run("update_product", {"product_id": "P77", "stock_qty": 3})


def test_sold_product_cannot_be_deleted():
    out = run("delete_product", {"product_id": "P01"})   # P01 is on a bill
    assert "REJECTED" in out
    assert product("P01") is not None


def test_bad_arguments_never_reach_the_database():
    # condition "used" fails the Pydantic model, before any tool code runs.
    # PydanticAI sends the validation error back to the model instead of calling the tool.
    out = run("add_product", new_product(condition="used"))
    assert "Input should be 'new' or 'refurbished'" in out
    assert product("P21") is None


def test_query_tool_refuses_writes():
    """Needs the local Neo4j; skipped if it is not running."""
    if isinstance(query_graph("RETURN 1 AS ok"), str):
        pytest.skip("Neo4j is not running")
    before = query_graph("MATCH (n) RETURN count(n) AS n")
    assert "Query failed" in query_graph("CREATE (:Hack {id: 'x'})")
    assert "Query failed" in query_graph("MATCH (n) DETACH DELETE n")
    assert query_graph("MATCH (n) RETURN count(n) AS n") == before
