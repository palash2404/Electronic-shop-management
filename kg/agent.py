"""A chat assistant for the shop's knowledge graph, built with PydanticAI.

  .venv/bin/python -m kg.agent

By default it talks to a local model served by Ollama, so no API key is needed:

  brew install ollama && brew services start ollama
  ollama pull qwen3:4b && ollama create eshop-qwen -f Modelfile

To use a hosted model instead, set ESHOP_MODEL and its API key in .env
(see .env.example).

The model never touches the data directly. It can only call the tools below:
  - query_graph        read-only Cypher against Neo4j
  - add_product        \\
  - update_product      > writes: confirmed by you, then validated with SHACL
  - delete_product     /           before anything is saved (kg/store.py)

So the worst a wrong model answer can do is propose a change that you decline
or that the shapes reject.
"""
import os
import uuid
from dataclasses import dataclass
from typing import Callable, Literal

from neo4j import READ_ACCESS
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from kg.store import Rejected, checked_write
from kg.tracing import flush, setup_tracing, trace
from kg.to_neo4j import driver

DEFAULT_MODEL = "ollama:eshop-qwen"   # local Qwen3 4b, see Modelfile; override with ESHOP_MODEL
MAX_ROWS = 50


INSTRUCTIONS = """\
You help the staff of an electronics shop work with its knowledge graph: products,
their components, the materials in those components, and sales.

Answering questions: call query_graph with a Cypher query. The Neo4j schema is:

  (:Product {id, name, category, condition, unit_price, stock_qty, release_year})
  (:Component {id, name, type, recyclable})
  (:Material {id, name, cas_number, regulation})   extra labels :Hazardous and :CriticalRaw
  (:Manufacturer {id, name, country})
  (:Customer {id, name, city})
  (:Bill {id, date})

  (:Product)-[:HAS_PART {quantity}]->(:Component)
  (:Component)-[:CONTAINS {mass_g}]->(:Material)
  (:Product|Component)-[:MADE_BY]->(:Manufacturer)
  (:Customer)-[:PLACED]->(:Bill)-[:INCLUDES {quantity, unit_price}]->(:Product)

Relationships only exist in the direction shown. The two paths you will need most:

  MATCH (p:Product)-[:HAS_PART]->(c:Component)-[:CONTAINS]->(m:Material)
  MATCH (cu:Customer)-[:PLACED]->(b:Bill)-[:INCLUDES]->(p:Product)

IDs look like P01 (product), C01 (component), M01 (material), MF01 (manufacturer).
condition is 'new' or 'refurbished'. Prices are in euro, masses in grams.
Names and categories start with a capital letter ('Lead', 'Smartphone'), so compare
them without regard to case: WHERE toLower(m.name) = 'lead'.
Base every answer on query results. If a query returns nothing, say so; do not guess.

Changing data: use add_product, update_product or delete_product. Look up IDs with
query_graph first instead of inventing them. Each change is shown to the user for
confirmation and then checked against the shop's data rules. If a change is declined
or rejected, tell the user plainly why, using the reasons you were given. Do not
retry with different values unless the user asks for that.
"""


@dataclass
class Deps:
    """What the tools need from the outside: a way to ask the user for a yes."""
    confirm: Callable[[str], bool]


class Part(BaseModel):
    component_id: str = Field(description="An existing component ID, e.g. C01")
    quantity: int = Field(default=1, ge=1)


class NewProduct(BaseModel):
    product_id: str = Field(pattern=r"^P\d{2,}$", description="A new, unused ID, e.g. P21")
    name: str = Field(min_length=1)
    category: str = Field(description="e.g. Smartphone, Laptop, Monitor")
    manufacturer_id: str = Field(description="An existing manufacturer ID, e.g. MF01")
    unit_price: float = Field(ge=0, description="Euro")
    stock_qty: int = Field(ge=0)
    release_year: int
    condition: Literal["new", "refurbished"] = "new"
    parts: list[Part] = Field(description="The components the product is built from")


agent = Agent(name="shop-assistant", deps_type=Deps, instructions=INSTRUCTIONS)


def _write(ctx: RunContext[Deps], summary: str, statements: list[tuple[str, tuple]]) -> str:
    """Shared path for every write tool: confirm, then validate and save."""
    if not ctx.deps.confirm(summary):
        return "DECLINED: the user did not confirm. Nothing was changed."
    try:
        return checked_write(statements)
    except Rejected as e:
        return "REJECTED, nothing was changed. Reasons:\n- " + "\n- ".join(e.reasons)


def run_settings() -> dict | None:
    """Optional cap on the length of one model reply (ESHOP_MAX_TOKENS).

    Free hosted plans limit output tokens per minute and refuse a request whose
    possible output is larger than that limit, so a cap is needed there.
    """
    cap = os.environ.get("ESHOP_MAX_TOKENS")
    return {"max_tokens": int(cap)} if cap else None


def _plain(value):
    """Neo4j dates and times are not JSON types; send them to the model as text."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value if isinstance(value, (str, int, float, bool, type(None))) else str(value)


@agent.tool_plain
def query_graph(cypher: str) -> list[dict] | str:
    """Run a read-only Cypher query against the Neo4j graph and return the rows.

    Use this for every question about products, components, materials or sales,
    and to look up IDs before a change. Write statements are refused.
    """
    try:
        with driver() as db, db.session(default_access_mode=READ_ACCESS) as session:
            rows = [_plain(r.data()) for r in session.run(cypher)]
    except Exception as e:  # syntax errors, write attempts, Neo4j not running
        return f"Query failed: {e}"
    if not rows:
        return ("0 rows. A wrong relationship direction or a misspelled name also gives 0 rows: "
                "check the query against the schema, and run a corrected one if you find a mistake.")
    if len(rows) > MAX_ROWS:
        return rows[:MAX_ROWS] + [{"note": f"{len(rows) - MAX_ROWS} more rows not shown; narrow the query"}]
    return rows


@agent.tool
def add_product(ctx: RunContext[Deps], product: NewProduct) -> str:
    """Add a new product together with its components."""
    p = product
    parts = ", ".join(f"{x.quantity}x {x.component_id}" for x in p.parts) or "no parts"
    statements = [("INSERT INTO product (product_id, name, category, manufacturer_id, unit_price,"
                   " stock_qty, release_year, item_condition) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (p.product_id, p.name, p.category, p.manufacturer_id, p.unit_price,
                    p.stock_qty, p.release_year, p.condition))]
    statements += [("INSERT INTO product_component (product_id, component_id, quantity) VALUES (?, ?, ?)",
                    (p.product_id, x.component_id, x.quantity)) for x in p.parts]
    return _write(ctx, f"Add {p.condition} product {p.product_id} '{p.name}' ({p.category}, "
                       f"{p.manufacturer_id}, €{p.unit_price:.2f}, stock {p.stock_qty}) with {parts}",
                  statements)


@agent.tool
def update_product(ctx: RunContext[Deps], product_id: str,
                   unit_price: float | None = None, stock_qty: int | None = None) -> str:
    """Change the price and/or the stock quantity of an existing product."""
    changes = {k: v for k, v in (("unit_price", unit_price), ("stock_qty", stock_qty)) if v is not None}
    if not changes:
        return "Nothing to change: give unit_price, stock_qty or both."
    sets = ", ".join(f"{column} = ?" for column in changes)
    return _write(ctx, f"Update {product_id}: " + ", ".join(f"{k} = {v}" for k, v in changes.items()),
                  [(f"UPDATE product SET {sets} WHERE product_id = ?", (*changes.values(), product_id))])


@agent.tool
def delete_product(ctx: RunContext[Deps], product_id: str) -> str:
    """Delete a product. Products that appear on a bill cannot be deleted."""
    return _write(ctx, f"DELETE product {product_id} and its component list",
                  [("DELETE FROM product WHERE product_id = ?", (product_id,))])


def ask_user(summary: str) -> bool:
    return input(f"\n  The assistant wants to: {summary}\n  Apply? [y/N] ").strip().lower() == "y"


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    model = os.environ.get("ESHOP_MODEL", DEFAULT_MODEL)
    tracing = setup_tracing()
    print(f"Shop assistant ({model}, Langfuse tracing {'on' if tracing else 'off'}). Empty line to quit.")

    # One chat is one Langfuse session; each question in it is one trace.
    session = f"chat-{uuid.uuid4().hex[:12]}"
    history = []
    try:
        while (question := input("\nYou: ").strip()):
            try:
                with trace("answer-question", input=question, session_id=session,
                           tags=["assistant"], metadata={"model": str(model)}) as t:
                    result = agent.run_sync(question, model=model, deps=Deps(confirm=ask_user),
                                            message_history=history, model_settings=run_settings())
                    t.update(output=result.output)
            except Exception as e:  # Ollama not running, missing API key, network
                print(f"Error: {e}")
                continue
            history = result.all_messages()
            print(f"\nAssistant: {result.output}")
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        flush()


if __name__ == "__main__":
    main()
