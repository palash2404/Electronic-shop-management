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
| 4 | SHACL validation (pyshacl) | done |
| 5 | Neo4j + Cypher (RDF loaded as a property graph) | done |
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

## Validation (stage 4)

[`graph/shapes.ttl`](graph/shapes.ttl) holds the SHACL shapes: the rules the data must follow. [`kg/validate.py`](kg/validate.py) checks a graph against them with pyshacl.

```bash
.venv/bin/python -m kg.validate                              # the shop data: valid, 1 warning
.venv/bin/python -m kg.validate graph/examples/invalid.ttl   # broken on purpose: 12 violations
```

The shapes cover:

- **Required values and counts**: every product has exactly one name, price and manufacturer.
- **Types and ranges**: prices are decimals of 0 or more, masses are above 0 grams.
- **Allowed values**: condition is `new` or `refurbished`.
- **Formats**: CAS numbers match `7439-92-1`, countries are two-letter codes.
- **Links that must resolve**: a product's manufacturer must exist in the graph as a `Manufacturer`.
- **Severity**: a material without a CAS number is a warning, not a violation.
- **A business rule in SPARQL**: a product sold as `new` must not contain a RoHS-restricted material.

OWL and SHACL do different jobs. The ontology adds facts (this product is hazardous). The shapes check facts (this product has no price). OWL would never complain about a missing price, because under the open-world assumption the price may simply be unknown.

`validate()` returns a list of findings, so the AI agent in stage 6 can check a change before writing it.

## Neo4j and Cypher (stage 5)

[`kg/to_neo4j.py`](kg/to_neo4j.py) loads `graph/data.ttl` into Neo4j, and [`graph/cypher/`](graph/cypher) holds six Cypher queries. The loader checks the data against the SHACL shapes first and refuses to load invalid data.

Setup on macOS, for a local practice database without a login:

```bash
brew install neo4j
# in /opt/homebrew/opt/neo4j/libexec/conf/neo4j.conf set: dbms.security.auth_enabled=false
neo4j start        # browser UI at http://localhost:7474, stop with: neo4j stop
```

For a database with a login, set `NEO4J_URI`, `NEO4J_USER` and `NEO4J_PASSWORD` instead.

```bash
.venv/bin/python -m kg.to_neo4j   # 1,433 triples -> 95 nodes, 243 relationships
.venv/bin/python -m kg.cypher     # list the queries
.venv/bin/python -m kg.cypher 5   # run one of them
```

The same facts are modeled differently in the two graph worlds:

| RDF | Neo4j |
|---|---|
| `ex:P01 a eshop:Product` | `(:Product {id: "P01"})` |
| `a eshop:HazardousMaterial` | a second label: `(:Material:Hazardous)` |
| extra node `ex:P01_C25` with `eshop:quantity 3` | `(P01)-[:HAS_PART {quantity: 3}]->(C25)` |

In RDF a link cannot carry a value, so quantities and masses needed extra nodes. In Neo4j a relationship has properties, so those nodes disappear: 1,433 triples become 95 nodes and 243 relationships.

The loader maps RDF to this model by hand instead of using the neosemantics (n10s) plugin. n10s imports triples as they are, which would keep the extra nodes; the hand-written mapping gives the model a Neo4j user would design.

All three query languages return the same answers on the shared questions (hazardous products, critical raw materials in stock, sales by category, sales with lead or cadmium):

```cypher
MATCH (p:Product)-[:HAS_PART]->(:Component)-[:CONTAINS]->(m:Hazardous)
RETURN p.name, collect(DISTINCT m.name)
```

Query 5 is a recall: which products use a faulty battery cell, how many are in stock, and which customers to notify.
