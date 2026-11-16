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
| 6 | AI agent with validated writes (PydanticAI, Langfuse) | done |
| 7 | Datasheet extraction + evaluation | done |

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

## AI assistant (stage 6)

[`kg/agent.py`](kg/agent.py) is a chat assistant built with PydanticAI. You ask questions in plain language and it answers from the graph; you ask for a change and it proposes one.

It runs on a local model by default, so it needs no API key and no data leaves the machine:

```bash
brew install ollama
brew services start ollama         # the local model server
ollama pull qwen3:4b               # 2.5 GB, runs in 8 GB RAM
ollama create eshop-qwen -f Modelfile   # the same model with a larger context window
.venv/bin/python -m kg.agent
```

The model never touches the data directly. It can only call four tools:

| Tool | What it does | Guard |
|---|---|---|
| `query_graph` | Runs Cypher against Neo4j | Read-only session: write statements fail |
| `add_product` | Adds a product with its components | Typed arguments (Pydantic), your confirmation, then SHACL |
| `update_product` | Changes price or stock | Your confirmation, then SHACL |
| `delete_product` | Deletes a product | Your confirmation, then database and SHACL rules |

Every write goes through [`kg/store.py`](kg/store.py), which validates before it commits:

1. Run the SQL inside an open transaction. SQLite checks keys and `CHECK` constraints.
2. Build the RDF graph from that uncommitted state.
3. Validate it against the SHACL shapes.
4. Commit only if there are no violations. Otherwise roll back and tell the model why.

After a commit, `graph/data.ttl` is rewritten and Neo4j is reloaded, so the three stores stay in step.

Example: the model tries to add a product sold as new that contains a leaded circuit board. SQL has no rule against it. The SHACL shape does, so nothing is saved and the assistant reports: *a product sold as 'new' must not contain a RoHS-restricted material*.

The default model is `ollama:eshop-qwen`: Qwen3 4b with the context window raised from Ollama's default of 4,096 tokens to 8,192 (see [`Modelfile`](Modelfile)). With the default window the instructions, tool definitions and query results do not fit, and Ollama drops the oldest text without an error. A 4-billion-parameter model is slow and makes more mistakes than a hosted one, which is exactly why the guards above matter: a wrong query returns an error, and a wrong change is declined or rejected. To use another model, copy `.env.example` to `.env` and set `ESHOP_MODEL` and the provider's key (for example `groq:qwen/qwen3.8-27b` with `GROQ_API_KEY`, or `anthropic:claude-haiku-5-5` with `ANTHROPIC_API_KEY`).

### Tracing with Langfuse

If `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set in `.env`, every run is traced to Langfuse: the prompt, each tool call with its arguments and result, token counts and cost. Without the keys the assistant runs untraced.

## Datasheet extraction (stage 7)

[`kg/extract.py`](kg/extract.py) reads a component datasheet or safety data sheet and turns it into a component with its materials. [`data/datasheets/`](data/datasheets) holds five sample sheets written for this project: a material declaration table, a safety data sheet with percentages, a legacy board in milligrams, a German datasheet in prose, and a panel that lists substances as "not detected".

```bash
.venv/bin/python -m kg.extract data/datasheets/ds02_lfp_cell.txt          # show what was read
.venv/bin/python -m kg.extract data/datasheets/ds02_lfp_cell.txt --save   # and import it
.venv/bin/python -m kg.extract data/datasheets/pdf/ds01_gan_power_pcb.pdf # PDFs work too
```

The work is split so that the model does as little as possible:

| Step | Who | What |
|---|---|---|
| Read | model | Fills in a fixed form: name, type, manufacturer, and each substance with its CAS number, amount and unit **as printed** |
| Convert | code | mg and percent to grams |
| Check | code | CAS check digit, which catches misread or invented numbers |
| Match | code | Known materials are found by CAS number, so "Kupfer" and "Copper" are the same material |
| Import | code | Through `kg/store.py`: validated with SHACL before anything is saved |

The form is a Pydantic class, and the model server is asked for JSON that fits its schema (`NativeOutput`), so even a small model returns a valid form.

## Evaluation (stage 7)

[`kg/evaluate.py`](kg/evaluate.py) scores the model on fixed inputs, so a change to a prompt or a model can be compared with the run before. No model judges a model: the scoring is plain code.

```bash
.venv/bin/python -m kg.evaluate extraction   # 5 datasheets against data/datasheets/gold.json
.venv/bin/python -m kg.evaluate questions    # 10 questions against answers computed with Cypher
```

- **Extraction** is compared with a hand-written answer key, material by material: precision, recall, whether the grams are right, whether the hazard flag is right, and the four component fields.
- **Questions** ([`eval/questions.json`](eval/questions.json)): each question comes with a hand-written Cypher query that returns the true answer. A reply is correct if it contains every expected value and names no other candidate.

Results are saved under [`eval/results/`](eval/results). The runs use Langfuse's experiment runner: with Langfuse keys in `.env` each run also appears in Langfuse with traces and scores; without keys it runs locally.

### Results with the local model

Qwen3 4b on an 8 GB MacBook (M1), measured on 16 Nov 2026:

| Datasheet extraction (5 sheets) | Score |
|---|---|
| Materials found (recall) | 1.00 |
| Materials that are really in the sheet (precision) | 1.00 |
| Mass in grams correct | 1.00 |
| Hazard flag correct | 1.00 |
| Component name, type, manufacturer, recyclable | 1.00 |
| Time per sheet | 23 to 30 s |

| Assistant, 10 questions | Correct | Time per question |
|---|---|---|
| Qwen3 4b, local | 9 of 10 | 34 to 306 s (median 2 min) |
| Qwen3.8 27b on Groq's free plan, two runs | 8 and 6 of 10 | 1 to 57 s |

The local model is slow but careful: its one miss was a query that returned nothing. The hosted model answers in seconds, but in one run it invented a manufacturer without querying the graph and once wrote a tool call as plain text. Two of its misses were not the model's fault: a reply cut short by the free plan's output limit, and a correct answer that also listed the runners-up, which the strict scorer counts as wrong.

What the evaluation showed while building this:

- **First prompt:** every material and mass was right, but the component fields scored 0.85. The model typed a circuit board as "cable" and used a document number as a name.
- **Describing the fields in the prompt** raised the fields to 1.00, and in the same run the hazard score fell to 0.85: on one sheet the model copied "not classified" into every hazard note. A repeat run did not do it. The fix is in code (such notes count as no hazard) plus temperature 0, and a test.
- **Thinking off:** Qwen3 writes out its reasoning before answering. For form filling that cost a lot and gained nothing: with the same prompt, thinking on took 118 to 281 s per sheet and scored 0.95 on the component fields, against 23 to 30 s and 1.00 with thinking off. It is now off for extraction with Ollama models (`ESHOP_THINK=1` turns it on). The assistant keeps thinking on: with it off, the model wrote its reasoning into the answers and was no faster.
- **A bug found by switching models:** the hosted model asked for a bill's date, and the query tool could not pass a Neo4j date on to the model. The local model had never asked for one. Fixed, with a test.
- **The code checks earn their place:** on the panel sheet the model listed two "not detected" substances with amount 0. The code leaves them out, so they never reach the graph.

These numbers come from five sheets and ten questions that were also used to improve the prompts, so they show that the pipeline works, not how it would do on unseen documents. Each assistant run was done once or twice, and the scores vary between runs.

## Tests

```bash
.venv/bin/python -m pytest -q
```

The tests need no API key. A scripted `FunctionModel` plays the model's part, so each test checks what happens to the data for a given tool call or a given filled-in form: valid changes are saved, declined and invalid ones are not. The scoring code is tested too. Everything runs on a temporary copy of the database.
