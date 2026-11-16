"""Load the RDF graph into Neo4j as a property graph.

  .venv/bin/python -m kg.to_neo4j

RDF and Neo4j model the same facts differently:

  RDF                                   Neo4j
  ------------------------------------  ------------------------------------
  everything is a triple                nodes and relationships have properties
  ex:P01 a eshop:Product                (:Product {id: "P01"})
  a eshop:HazardousMaterial             a second label, (:Material:Hazardous)
  ex:P01_C25 with eshop:quantity 3      (P01)-[:HAS_PART {quantity: 3}]->(C25)

The last row is the important one. RDF needed an extra node to hold the
quantity. In Neo4j the relationship itself holds it, so the PartUsage,
MaterialContent and BillLine nodes disappear.

The data is checked against the SHACL shapes first. Invalid data is not loaded.
This replaces everything in the Neo4j database it connects to.
"""
import os
import sys

from neo4j import GraphDatabase
from rdflib import Graph

from kg.query import GRAPH_DIR
from kg.validate import validate

PREFIXES = """
PREFIX eshop: <http://example.org/eshop#>
PREFIX ex:    <http://example.org/eshop/id/>
PREFIX rdfs:  <http://www.w3.org/2000/01/rdf-schema#>
"""
ID = 'BIND(STRAFTER(STR(?s), STR(ex:)) AS ?id)'

# One step per kind of node or relationship: a SPARQL query that reads rows
# out of the RDF graph, and a Cypher statement that writes each row to Neo4j.
STEPS = [
    ("manufacturers",
     f"SELECT ?id ?name ?country WHERE {{ ?s a eshop:Manufacturer ; rdfs:label ?name ; eshop:country ?country . {ID} }}",
     "CREATE (:Manufacturer {id: row.id, name: row.name, country: row.country})"),

    ("materials",
     f"""SELECT ?id ?name ?cas ?regulation ?hazardous ?critical WHERE {{
           ?s a eshop:Material ; rdfs:label ?name . {ID}
           OPTIONAL {{ ?s eshop:casNumber ?cas }}
           OPTIONAL {{ ?s eshop:regulation ?regulation }}
           BIND(EXISTS {{ ?s a eshop:HazardousMaterial }} AS ?hazardous)
           BIND(EXISTS {{ ?s a eshop:CriticalRawMaterial }} AS ?critical) }}""",
     """CREATE (m:Material {id: row.id, name: row.name})
        SET m.cas_number = row.cas, m.regulation = row.regulation
        FOREACH (_ IN CASE WHEN row.hazardous THEN [1] ELSE [] END | SET m:Hazardous)
        FOREACH (_ IN CASE WHEN row.critical  THEN [1] ELSE [] END | SET m:CriticalRaw)"""),

    ("components",
     f"""SELECT ?id ?name ?type ?recyclable ?maker WHERE {{
           ?s a eshop:Component ; rdfs:label ?name ; eshop:componentType ?type ; eshop:recyclable ?recyclable . {ID}
           OPTIONAL {{ ?s eshop:manufacturedBy ?m . BIND(STRAFTER(STR(?m), STR(ex:)) AS ?maker) }} }}""",
     """CREATE (c:Component {id: row.id, name: row.name, type: row.type, recyclable: row.recyclable})
        WITH c, row MATCH (m:Manufacturer {id: row.maker})
        CREATE (c)-[:MADE_BY]->(m)"""),

    ("products",
     f"""SELECT ?id ?name ?category ?condition ?price ?stock ?year ?maker WHERE {{
           ?s a eshop:Product ; rdfs:label ?name ; eshop:category ?category ;
              eshop:itemCondition ?condition ; eshop:unitPrice ?price ; eshop:stockQty ?stock ;
              eshop:releaseYear ?year ; eshop:manufacturedBy ?m . {ID}
           BIND(STRAFTER(STR(?m), STR(ex:)) AS ?maker) }}""",
     """MATCH (m:Manufacturer {id: row.maker})
        CREATE (p:Product {id: row.id, name: row.name, category: row.category, condition: row.condition,
                           unit_price: row.price, stock_qty: row.stock, release_year: row.year})
        CREATE (p)-[:MADE_BY]->(m)"""),

    ("HAS_PART",
     """SELECT ?product ?component ?quantity WHERE {
          ?p eshop:hasPartUsage ?u . ?u eshop:usedComponent ?c ; eshop:quantity ?quantity .
          BIND(STRAFTER(STR(?p), STR(ex:)) AS ?product) BIND(STRAFTER(STR(?c), STR(ex:)) AS ?component) }""",
     """MATCH (p:Product {id: row.product}), (c:Component {id: row.component})
        CREATE (p)-[:HAS_PART {quantity: row.quantity}]->(c)"""),

    ("CONTAINS",
     """SELECT ?component ?material ?mass WHERE {
          ?c eshop:hasMaterialContent ?mc . ?mc eshop:material ?m ; eshop:massGrams ?mass .
          BIND(STRAFTER(STR(?c), STR(ex:)) AS ?component) BIND(STRAFTER(STR(?m), STR(ex:)) AS ?material) }""",
     """MATCH (c:Component {id: row.component}), (m:Material {id: row.material})
        CREATE (c)-[:CONTAINS {mass_g: row.mass}]->(m)"""),

    ("customers",
     f"SELECT ?id ?name ?city WHERE {{ ?s a eshop:Customer ; rdfs:label ?name ; eshop:city ?city . {ID} }}",
     "CREATE (:Customer {id: row.id, name: row.name, city: row.city})"),

    ("bills",
     f"""SELECT ?id ?date ?customer WHERE {{
           ?s a eshop:Bill ; eshop:billDate ?date ; eshop:billedTo ?c . {ID}
           BIND(STRAFTER(STR(?c), STR(ex:)) AS ?customer) }}""",
     """MATCH (c:Customer {id: row.customer})
        CREATE (c)-[:PLACED]->(:Bill {id: row.id, date: date(row.date)})"""),

    ("INCLUDES",
     """SELECT ?bill ?product ?quantity ?price WHERE {
          ?b eshop:hasLine ?l . ?l eshop:soldProduct ?p ; eshop:quantity ?quantity ; eshop:unitPrice ?price .
          BIND(STRAFTER(STR(?b), STR(ex:)) AS ?bill) BIND(STRAFTER(STR(?p), STR(ex:)) AS ?product) }""",
     """MATCH (b:Bill {id: row.bill}), (p:Product {id: row.product})
        CREATE (b)-[:INCLUDES {quantity: row.quantity, unit_price: row.price}]->(p)"""),
]

UNIQUE_ID = ["Manufacturer", "Material", "Component", "Product", "Customer", "Bill"]


def driver():
    """Connect to the local Neo4j. Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD to override."""
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user, password = os.environ.get("NEO4J_USER"), os.environ.get("NEO4J_PASSWORD")
    return GraphDatabase.driver(uri, auth=(user, password) if user else None)


def plain(value):
    """An RDF literal as a value Neo4j can store. Decimals become floats, dates stay text."""
    if value is None:
        return None
    py = value.toPython()
    return py if isinstance(py, (bool, int, str)) else float(py) if hasattr(py, "as_tuple") else str(py)


def load(data: Graph, verbose: bool = False) -> tuple[int, int]:
    """Replace the Neo4j database with this RDF graph. Returns (nodes, relationships)."""
    with driver() as db, db.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        for label in UNIQUE_ID:
            session.run(f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS "
                        f"FOR (n:{label}) REQUIRE n.id IS UNIQUE")
        for name, sparql, cypher in STEPS:
            result = data.query(PREFIXES + sparql)
            rows = [{str(v): plain(row[v]) for v in result.vars} for row in result]
            session.run(f"UNWIND $rows AS row {cypher}", rows=rows)
            if verbose:
                print(f"  {name:<14} {len(rows)}")
        nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    return nodes, rels


def main() -> None:
    data = Graph().parse(GRAPH_DIR / "data.ttl")
    ok, findings = validate(data)
    if not ok:
        sys.exit(f"Not loading: the data has {len(findings)} SHACL findings. Run kg.validate.")
    nodes, rels = load(data, verbose=True)
    print(f"Loaded {nodes} nodes and {rels} relationships from {len(data)} triples.")


if __name__ == "__main__":
    main()
