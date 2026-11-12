# Electronics Knowledge Graph

An electronics shop database that grows, step by step, into a validated knowledge graph with an AI assistant on top.

The shop is modeled around the circular economy: **products** are built from **components**, components contain **materials**, and some materials are **hazardous** (RoHS, CLP) or **critical raw materials** under EU rules. Questions like *"which products we sold last month contain lead or cadmium?"* need several joins in SQL but are a single path query in a graph. That's the reason for the project.

The full plan with the pipeline diagram is in [`docs/pipeline-plan.html`](docs/pipeline-plan.html).

## Roadmap

| Stage | What | Status |
|---|---|---|
| 1 | Relational schema + seed data (SQLite) | done |
| 2 | OWL ontology | done |
| 3 | RDF conversion (rdflib) + SPARQL queries | done |
| 4 | SHACL validation (pyshacl) | planned |
| 5 | Neo4j + Cypher (neosemantics import) | planned |
| 6 | AI agent with validated writes (PydanticAI, Langfuse) | planned |
| 7 | Datasheet extraction + evaluation | planned |

## Data model (stage 1)

```
manufacturer ─┬─< product >─┬─ product_component ─< component >─ component_material ─< material
              └─< component │
customer ─< bill ─< bill_item >─┘
```

- 20 products (new and refurbished), 27 components, 21 materials, 7 manufacturers
- Each component lists its materials in grams per unit
- Refurbished legacy items carry real legacy hazards: leaded solder, CCFL backlights with mercury, NiCd batteries with cadmium, brominated flame retardants

Brands are fictional and material masses are approximate, illustrative values. CAS numbers and regulation references are real.

## Setup

Needs only Python 3.10+; SQLite is built in.

```bash
python3 db.py      # creates eshop.db from sql/schema.sql and sql/seed.sql
python3 esms.py    # start the shop CLI
```

Running `db.py` again resets the database to the seed data.

For the graph stages, install the Python packages into a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## CLI

- **Products**: list, add, update price or stock, delete, show components
- **Customers**: list, add, update, delete
- **Bills**: list with totals, create a multi-item bill (one transaction, reduces stock)
- **Reports**: products with hazardous materials, sales by category, grams of critical raw materials in stock, CSV export

## Knowledge graph (stages 2 and 3)

| File | What it is |
|---|---|
| [`graph/ontology.ttl`](graph/ontology.ttl) | The OWL ontology: classes and properties, written by hand |
| [`graph/data.ttl`](graph/data.ttl) | The shop data as RDF triples, generated from SQLite |
| [`graph/queries/`](graph/queries) | Five SPARQL queries |
| [`kg/to_rdf.py`](kg/to_rdf.py) | Converts the database to RDF |
| [`kg/query.py`](kg/query.py) | Runs a query file and prints a table |
| [`kg/reason.py`](kg/reason.py) | Runs an OWL RL reasoner (owlrl) over the graph |

```bash
.venv/bin/python -m kg.to_rdf     # SQLite -> graph/data.ttl (1,433 triples)
.venv/bin/python -m kg.query      # list the queries
.venv/bin/python -m kg.query 1    # run one of them
.venv/bin/python -m kg.reason     # show what the reasoner infers
```

The hazardous-products report needs four joins in SQL. In SPARQL it is one path:

```sparql
?product eshop:hasPart/eshop:containsMaterial ?material .
?material a eshop:HazardousMaterial .
```

The ontology goes one step further and *defines* a hazardous product as a product that contains some hazardous material. No product is marked hazardous in the data. The reasoner derives it: 0 hazardous products before reasoning, 16 after, the same 16 the SQL report finds.

Modeling choices worth knowing:

- A boolean column (`is_hazardous`) becomes class membership (`a eshop:HazardousMaterial`).
- A `NULL` becomes a missing triple. RDF has no null.
- A join table with an extra column (`quantity`, `mass_g`) becomes a direct link plus a node that carries the number (`PartUsage`, `MaterialContent`).
- `containsMaterial` has no `rdfs:domain`. In OWL a domain is an inference rule, not a check, so a domain of `Component` would make every product a component.
