"""Convert the SQLite shop database into RDF triples (graph/data.ttl).

Run from the project root:  .venv/bin/python -m kg.to_rdf
"""
from decimal import Decimal
from pathlib import Path

from rdflib import RDF, RDFS, XSD, Graph, Literal, Namespace

from db import query

GRAPH_DIR = Path(__file__).parent.parent / "graph"
DATA_PATH = GRAPH_DIR / "data.ttl"

ESHOP = Namespace("http://example.org/eshop#")    # vocabulary: classes and properties
EX = Namespace("http://example.org/eshop/id/")    # data: one IRI per row


def dec(value) -> Literal:
    return Literal(Decimal(str(value)), datatype=XSD.decimal)


def build() -> Graph:
    g = Graph()
    g.bind("eshop", ESHOP)
    g.bind("ex", EX)

    for r in query("SELECT * FROM manufacturer"):
        s = EX[r["manufacturer_id"]]
        g.add((s, RDF.type, ESHOP.Manufacturer))
        g.add((s, RDFS.label, Literal(r["name"])))
        g.add((s, ESHOP.country, Literal(r["country"])))

    for r in query("SELECT * FROM material"):
        s = EX[r["material_id"]]
        g.add((s, RDF.type, ESHOP.Material))
        g.add((s, RDFS.label, Literal(r["name"])))
        # A boolean column becomes class membership.
        if r["is_hazardous"]:
            g.add((s, RDF.type, ESHOP.HazardousMaterial))
        if r["is_critical_raw"]:
            g.add((s, RDF.type, ESHOP.CriticalRawMaterial))
        # NULL becomes "no triple": RDF has no null.
        if r["cas_number"]:
            g.add((s, ESHOP.casNumber, Literal(r["cas_number"])))
        if r["regulation"]:
            g.add((s, ESHOP.regulation, Literal(r["regulation"])))

    for r in query("SELECT * FROM component"):
        s = EX[r["component_id"]]
        g.add((s, RDF.type, ESHOP.Component))
        g.add((s, RDFS.label, Literal(r["name"])))
        g.add((s, ESHOP.componentType, Literal(r["component_type"])))
        g.add((s, ESHOP.recyclable, Literal(bool(r["recyclable"]))))
        if r["manufacturer_id"]:
            g.add((s, ESHOP.manufacturedBy, EX[r["manufacturer_id"]]))

    for r in query("SELECT * FROM product"):
        s = EX[r["product_id"]]
        g.add((s, RDF.type, ESHOP.Product))
        g.add((s, RDFS.label, Literal(r["name"])))
        g.add((s, ESHOP.category, Literal(r["category"])))
        g.add((s, ESHOP.itemCondition, Literal(r["item_condition"])))
        g.add((s, ESHOP.unitPrice, dec(r["unit_price"])))
        g.add((s, ESHOP.stockQty, Literal(r["stock_qty"])))
        g.add((s, ESHOP.releaseYear, Literal(r["release_year"])))
        g.add((s, ESHOP.manufacturedBy, EX[r["manufacturer_id"]]))

    # A join table with an extra column becomes two things: a direct link
    # (easy to query) and a node that carries the number.
    for r in query("SELECT * FROM product_component"):
        product, component = EX[r["product_id"]], EX[r["component_id"]]
        usage = EX[f"{r['product_id']}_{r['component_id']}"]
        g.add((product, ESHOP.hasPart, component))
        g.add((product, ESHOP.hasPartUsage, usage))
        g.add((usage, RDF.type, ESHOP.PartUsage))
        g.add((usage, ESHOP.usedComponent, component))
        g.add((usage, ESHOP.quantity, Literal(r["quantity"])))

    for r in query("SELECT * FROM component_material"):
        component, material = EX[r["component_id"]], EX[r["material_id"]]
        content = EX[f"{r['component_id']}_{r['material_id']}"]
        g.add((component, ESHOP.containsMaterial, material))
        g.add((component, ESHOP.hasMaterialContent, content))
        g.add((content, RDF.type, ESHOP.MaterialContent))
        g.add((content, ESHOP.material, material))
        g.add((content, ESHOP.massGrams, dec(r["mass_g"])))

    for r in query("SELECT * FROM customer"):
        s = EX[f"customer{r['customer_id']}"]
        g.add((s, RDF.type, ESHOP.Customer))
        g.add((s, RDFS.label, Literal(r["name"])))
        g.add((s, ESHOP.city, Literal(r["city"])))

    for r in query("SELECT * FROM bill"):
        s = EX[f"bill{r['bill_id']}"]
        g.add((s, RDF.type, ESHOP.Bill))
        g.add((s, ESHOP.billedTo, EX[f"customer{r['customer_id']}"]))
        g.add((s, ESHOP.billDate, Literal(r["bill_date"], datatype=XSD.date)))

    for r in query("SELECT * FROM bill_item"):
        bill = EX[f"bill{r['bill_id']}"]
        line = EX[f"bill{r['bill_id']}_{r['product_id']}"]
        g.add((bill, ESHOP.hasLine, line))
        g.add((line, RDF.type, ESHOP.BillLine))
        g.add((line, ESHOP.soldProduct, EX[r["product_id"]]))
        g.add((line, ESHOP.quantity, Literal(r["quantity"])))
        g.add((line, ESHOP.unitPrice, dec(r["unit_price"])))

    return g


if __name__ == "__main__":
    g = build()
    g.serialize(DATA_PATH, format="turtle")
    print(f"Wrote {len(g)} triples to {DATA_PATH.relative_to(GRAPH_DIR.parent)}")
