"""Check the graph against the SHACL shapes in graph/shapes.ttl.

  .venv/bin/python -m kg.validate                              check graph/data.ttl
  .venv/bin/python -m kg.validate graph/examples/invalid.ttl   check another file

Exit code is 0 if there are no violations (warnings are allowed), 1 otherwise.
"""
import sys
from pathlib import Path

from pyshacl import validate as shacl_validate
from rdflib import RDF, SH, Graph, URIRef

from kg.query import GRAPH_DIR

SHAPES_PATH = GRAPH_DIR / "shapes.ttl"
ONTOLOGY_PATH = GRAPH_DIR / "ontology.ttl"


def validate(data: Graph) -> tuple[bool, list[dict]]:
    """Return (ok, findings). ok is False if any finding is a violation.

    Each finding is a dict: severity, node, path, value, message.
    """
    shapes = Graph().parse(SHAPES_PATH)
    # The ontology is passed along so that subclasses count, for example a
    # HazardousMaterial is accepted where a Material is required.
    ontology = Graph().parse(ONTOLOGY_PATH)
    _, report, _ = shacl_validate(data, shacl_graph=shapes, ont_graph=ontology)

    def short(term) -> str:
        """ex:P01 for an IRI, the plain value for a literal, '' for nothing."""
        if term is None:
            return ""
        return data.namespace_manager.normalizeUri(term) if isinstance(term, URIRef) else str(term)

    findings = []
    for result in report.subjects(RDF.type, SH.ValidationResult):
        findings.append({
            "severity": report.value(result, SH.resultSeverity).split("#")[-1],
            "node": short(report.value(result, SH.focusNode)),
            "path": short(report.value(result, SH.resultPath)),
            "value": short(report.value(result, SH.value)),
            "message": str(report.value(result, SH.resultMessage)),
        })
    findings.sort(key=lambda f: (f["severity"], f["node"], f["path"]))
    return not any(f["severity"] == "Violation" for f in findings), findings


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "graph/data.ttl")
    data = Graph().parse(path)
    ok, findings = validate(data)

    violations = sum(f["severity"] == "Violation" for f in findings)
    print(f"{path}: {len(data)} triples, {violations} violations, "
          f"{len(findings) - violations} warnings")
    for f in findings:
        where = " ".join(x for x in (f["node"], f["path"]) if x)
        value = f" (value: {f['value']})" if f["value"] else ""
        print(f"  {f['severity']:<9} {where}{value}\n            {f['message']}")
    print("VALID" if ok else "INVALID")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
