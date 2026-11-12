"""Reasoner demo: derive new triples from the ontology's rules.

  .venv/bin/python -m kg.reason

Nothing in data.ttl says that a product is hazardous or that a product contains
a material. Both follow from the ontology:
  - the property chain:  hasPart + containsMaterial  =>  containsMaterial
  - the class definition: Product that contains some HazardousMaterial
                          =>  HazardousProduct
"""
import owlrl
from rdflib import RDF, Graph

from kg.query import load, show
from kg.to_rdf import ESHOP

ASK_HAZARDOUS = """
PREFIX eshop: <http://example.org/eshop#>
PREFIX rdfs:  <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?product ?name WHERE {
  ?product a eshop:HazardousProduct ; rdfs:label ?name .
} ORDER BY ?product"""


def infer(g: Graph) -> Graph:
    """Add every triple that follows under the OWL 2 RL rules, in place."""
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, axiomatic_triples=False,
                           datatype_axioms=False).expand(g)
    return g


def count(g: Graph, cls) -> int:
    return len(set(g.subjects(RDF.type, cls)))


def main() -> None:
    g = load()
    before = len(g)
    print(f"Before reasoning: {before} triples, "
          f"{count(g, ESHOP.HazardousProduct)} hazardous products, "
          f"{count(g, ESHOP.HazardousComponent)} hazardous components")
    infer(g)
    print(f"After reasoning:  {len(g)} triples (+{len(g) - before}), "
          f"{count(g, ESHOP.HazardousProduct)} hazardous products, "
          f"{count(g, ESHOP.HazardousComponent)} hazardous components\n")
    show(g, g.query(ASK_HAZARDOUS))


if __name__ == "__main__":
    main()
