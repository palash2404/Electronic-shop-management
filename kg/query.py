"""Run a SPARQL query file against the graph and print the result as a table.

  .venv/bin/python -m kg.query                 list the queries
  .venv/bin/python -m kg.query 1               run the query whose name starts with 1
  .venv/bin/python -m kg.query 1 --reason      same, after running the reasoner
"""
import sys
from pathlib import Path

from rdflib import Graph, URIRef

GRAPH_DIR = Path(__file__).parent.parent / "graph"
QUERY_DIR = GRAPH_DIR / "queries"


def load() -> Graph:
    """The ontology and the data are just two files of triples in one graph."""
    g = Graph()
    g.parse(GRAPH_DIR / "ontology.ttl")
    g.parse(GRAPH_DIR / "data.ttl")
    return g


def show(g: Graph, result) -> None:
    def text(term) -> str:
        if term is None:
            return ""
        # Print ex:P01 rather than the full IRI.
        return g.namespace_manager.normalizeUri(term) if isinstance(term, URIRef) else str(term)

    cols = [str(v) for v in result.vars]
    rows = [[text(row[c]) for c in cols] for row in result]
    if not rows:
        print("(no rows)")
        return
    widths = [max(len(c), *(len(r[i]) for r in rows)) for i, c in enumerate(cols)]
    print("  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(v.ljust(w) for v, w in zip(r, widths)))
    print(f"({len(rows)} rows)")


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--reason"]
    files = sorted(QUERY_DIR.glob("*.rq"))
    if not args:
        print("Queries:", *(f"  {f.stem}" for f in files), sep="\n")
        return
    matches = [f for f in files if f.stem.startswith(args[0])]
    if len(matches) != 1:
        sys.exit(f"No single query starts with '{args[0]}'.")
    g = load()
    if "--reason" in sys.argv:
        from kg.reason import infer
        infer(g)
    show(g, g.query(matches[0].read_text()))


if __name__ == "__main__":
    main()
