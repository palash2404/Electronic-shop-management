"""The only way the agent may change data: validate first, then commit.

A change is a list of SQL statements. checked_write():
  1. runs them inside one open transaction (SQLite checks keys and CHECKs),
  2. builds the RDF graph from that uncommitted state,
  3. validates the graph against the SHACL shapes,
  4. commits only if there are no violations; otherwise everything rolls back.

After a commit it rewrites graph/data.ttl and reloads Neo4j, so all three
stores stay in step. SQLite is the source of truth.
"""
from db import Error, cursor
from kg.to_rdf import DATA_PATH, build
from kg.validate import validate


class Rejected(Exception):
    """The change broke a rule. Nothing was saved."""

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def sync_neo4j(graph) -> str:
    """Reload Neo4j from the graph. A stopped Neo4j does not undo the saved change."""
    try:
        from kg.to_neo4j import load
        nodes, rels = load(graph)
        return f"Neo4j reloaded ({nodes} nodes, {rels} relationships)."
    except Exception as e:  # driver errors, connection refused
        return f"Neo4j was not updated ({type(e).__name__}). Run kg.to_neo4j when it is up."


def checked_write(statements: list[tuple[str, tuple]]) -> str:
    """Apply the statements if the result is valid. Raises Rejected otherwise."""
    try:
        with cursor(commit=True) as cur:
            changed = 0
            for sql, params in statements:
                cur.execute(sql, params)
                changed += cur.rowcount
            if changed == 0:
                raise Rejected(["Nothing matched, so nothing was changed. Check the ID."])
            graph = build(lambda sql: cur.execute(sql).fetchall())
            ok, findings = validate(graph)
            if not ok:
                raise Rejected([f"{f['node']} {f['path']}: {f['message']}".replace("  ", " ")
                                for f in findings if f["severity"] == "Violation"])
    except Error as e:
        raise Rejected([f"Database constraint: {e}"]) from e

    graph.serialize(DATA_PATH, format="turtle")
    return "Saved. " + sync_neo4j(graph)
