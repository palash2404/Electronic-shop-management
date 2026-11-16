"""Run a Cypher query file against Neo4j and print the result as a table.

  .venv/bin/python -m kg.cypher        list the queries
  .venv/bin/python -m kg.cypher 1      run the query whose name starts with 1
"""
import sys

from kg.query import GRAPH_DIR, table
from kg.to_neo4j import driver

QUERY_DIR = GRAPH_DIR / "cypher"


def text(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return "" if value is None else str(value)


def main() -> None:
    files = sorted(QUERY_DIR.glob("*.cypher"))
    if len(sys.argv) < 2:
        print("Queries:", *(f"  {f.stem}" for f in files), sep="\n")
        return
    matches = [f for f in files if f.stem.startswith(sys.argv[1])]
    if len(matches) != 1:
        sys.exit(f"No single query starts with '{sys.argv[1]}'.")
    with driver() as db:
        records, _, keys = db.execute_query(matches[0].read_text())
    table(keys, [[text(r[k]) for k in keys] for r in records])


if __name__ == "__main__":
    main()
