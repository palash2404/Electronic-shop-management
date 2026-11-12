# Electronics Knowledge Graph

An electronics shop database that grows, step by step, into a validated knowledge graph with an AI assistant on top.

The shop is modeled around the circular economy: **products** are built from **components**, components contain **materials**, and some materials are **hazardous** (RoHS, CLP) or **critical raw materials** under EU rules. Questions like *"which products we sold last month contain lead or cadmium?"* need several joins in SQL but are a single path query in a graph. That's the reason for the project.

The full plan with the pipeline diagram is in [`docs/pipeline-plan.html`](docs/pipeline-plan.html).

## Roadmap

| Stage | What | Status |
|---|---|---|
| 1 | Relational schema + seed data (SQLite) | done |
| 2 | OWL ontology | planned |
| 3 | RDF conversion (rdflib) + SPARQL queries | planned |
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

## CLI

- **Products**: list, add, update price or stock, delete, show components
- **Customers**: list, add, update, delete
- **Bills**: list with totals, create a multi-item bill (one transaction, reduces stock)
- **Reports**: products with hazardous materials, sales by category, grams of critical raw materials in stock, CSV export
