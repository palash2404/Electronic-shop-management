# Electronics knowledge graph

A small electronics shop database that grows, one stage at a time, into a knowledge graph of what every product is made of: its components, the materials inside them in grams, and which of those materials are hazardous (RoHS, CLP) or on the EU list of critical raw materials. On top of the graph there is an AI assistant that answers questions and proposes changes, and a tool that reads component datasheets into the graph.

Why a graph: "which products did we sell last month that contain lead?" takes six joins in SQL and one path query in a graph.

Brands are invented and material masses are approximate. CAS numbers and regulations are real.

## The plan

| Stage | What | Built with |
|---|---|---|
| 1 | Shop database: products, components, materials, customers, bills | SQLite |
| 2 | Ontology: what the data means, plus rules a reasoner applies. It finds the 16 hazardous products without anyone marking them | OWL, owlrl |
| 3 | The database converted to RDF triples and queried with SPARQL | rdflib |
| 4 | Data rules checked before anything is saved, for example "a product sold as new must not contain a RoHS material" | SHACL, pyshacl |
| 5 | The validated graph loaded into a graph database | Neo4j, Cypher |
| 6 | Chat assistant that queries the graph and proposes changes. A person confirms every change and SHACL checks it before it is saved | PydanticAI, Ollama, Groq, Langfuse |
| 7 | Reading datasheets and safety data sheets into the graph, and measuring how well the model does it | PydanticAI, pypdf, Langfuse |

Changes flow one way: into SQLite, checked as a graph, then written to `graph/data.ttl` and Neo4j. The full plan with a diagram is in [`docs/pipeline-plan.html`](docs/pipeline-plan.html).

## What we used

| Tool | Used for |
|---|---|
| Python 3.10+ and SQLite | the shop data, the source of truth |
| rdflib, owlrl | RDF, SPARQL, OWL reasoning |
| pyshacl | SHACL validation |
| Neo4j and its Python driver | the property graph and Cypher queries |
| PydanticAI and Pydantic | the assistant, its typed tools, the datasheet form |
| Ollama with Qwen3 4b | local model, no API key needed |
| Groq (optional) | a faster hosted model |
| Langfuse | tracing and evaluation runs |
| pypdf | reading PDF datasheets |
| pytest | 45 tests that run without a model |

## Results

On the local Qwen3 4b model the assistant answered 9 of 10 test questions correctly, and all 5 sample datasheets were extracted without a mistake. The test set is small and was also used to improve the prompts, so these numbers show the pipeline works, not how it would do on new documents.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
python3 db.py                          # create the database
.venv/bin/python -m kg.to_rdf          # SQLite to RDF
.venv/bin/python -m kg.validate        # SHACL check
.venv/bin/python -m kg.to_neo4j        # load Neo4j (start it first: neo4j start)
ollama pull qwen3:4b && ollama create eshop-qwen -f Modelfile
.venv/bin/python -m kg.agent           # chat with the assistant
.venv/bin/python -m pytest -q          # tests
```

Model choice and API keys go in `.env`; copy `.env.example` to start.
