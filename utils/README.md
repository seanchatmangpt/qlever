# QLever Python Utils

Pure-Python utilities for querying and working with
[QLever](https://github.com/ad-freiburg/qlever) SPARQL endpoints.
No external dependencies — only the Python standard library.

---

## Installation

Clone the repository and add the project root to your `PYTHONPATH`:

```bash
git clone https://github.com/ad-freiburg/qlever.git
cd qlever
export PYTHONPATH="$PWD:$PYTHONPATH"
```

Python 3.8 or later is required.

---

## Quick Start

Five lines to your first query result:

```python
from utils import QLeverClient, select

client = QLeverClient("http://localhost:7001")
sparql = select("?s", "?p", "?o").where("?s ?p ?o .").limit(10).build()
rows   = client.query_df(sparql)
print(rows)
```

---

## Module Overview

| Module            | Purpose                                                        |
|-------------------|----------------------------------------------------------------|
| `client`          | Synchronous HTTP client (`QLeverClient`) for SPARQL queries    |
| `async_client`    | Async client (`AsyncQLeverClient`) with batch and pagination   |
| `rdf_utils`       | IRI/literal helpers, prefix management, N-Triples parser       |
| `sparql_builder`  | Fluent API for building SELECT / ASK / CONSTRUCT queries       |
| `templates`       | Pre-built SPARQL query templates for common KG patterns        |
| `cli`             | Command-line interface for running queries from the shell      |

---

## API Reference

### `QLeverClient`

```python
client = QLeverClient(endpoint, max_send=5000, timeout=300.0)
```

| Method / Attribute          | Description                                                   |
|-----------------------------|---------------------------------------------------------------|
| `query(sparql, action)`     | Execute a SPARQL string; returns dict (JSON) or str (text)    |
| `query_df(sparql)`          | Execute and return results as `List[Dict[str, str]]`          |
| `stats()`                   | Fetch server index statistics                                 |
| `cache_stats()`             | Fetch query-cache statistics                                  |
| `clear_cache(token)`        | Clear the server query cache (requires access token)          |

### `AsyncQLeverClient`

```python
async with AsyncQLeverClient(endpoint) as client:
    result = await client.query(sparql)
```

| Method                         | Description                                                  |
|--------------------------------|--------------------------------------------------------------|
| `query(sparql)`                | Execute a single SPARQL query asynchronously                 |
| `batch_query(queries)`         | Execute a list of queries in parallel via `asyncio.gather`   |
| `stream_query(sparql)`         | Async-iterate over result rows one at a time                 |
| `paginate(sparql, page_size)`  | Auto-paginate with LIMIT/OFFSET; yields pages                |

### `PrefixMap` (`rdf_utils`)

```python
pm = PrefixMap(include_common=True)  # loads rdf, rdfs, xsd, owl, schema, wd, wdt
pm.add("ex", "http://example.org/")
pm.expand("ex:thing")        # -> '<http://example.org/thing>'
pm.shorten("<http://...>")   # -> 'ex:...'
pm.to_sparql_prefixes()      # -> multiline PREFIX ... string
```

### RDF helpers (`rdf_utils`)

| Function                          | Description                                              |
|-----------------------------------|----------------------------------------------------------|
| `iri(value)`                      | Wrap a string in `< >` to form an IRI                   |
| `literal(value, lang, datatype)`  | Build an RDF literal with optional lang-tag or datatype  |
| `escape_sparql_string(value)`     | Escape special chars for safe embedding in SPARQL        |
| `parse_ntriples(text)`            | Parse N-Triples text into `(s, p, o)` tuples            |
| `parse_ntriples_line(line)`       | Parse a single N-Triples line                            |

### `sparql_builder` — Fluent query builder

```python
from utils import select, ask, construct

query = (
    select("?entity", "(COUNT(?p) AS ?degree)")
    .prefix("rdfs", "http://www.w3.org/2000/01/rdf-schema#")
    .where("?entity ?p ?o .")
    .filter('LANG(?label) = "en"')
    .group_by("?entity")
    .order_by("DESC(?degree)")
    .limit(20)
    .build()
)
```

Additional helpers: `insert_data(triples)`, `delete_data(triples)`,
`update(delete, insert, where)`, `values_block(vars, rows)`,
`service_clause(endpoint, pattern)`, `GraphManager`.

### `templates` — Pre-built SPARQL templates

All functions return ready-to-use SPARQL strings.

**Knowledge Graph Exploration**

| Function                               | Returns                                           |
|----------------------------------------|---------------------------------------------------|
| `entity_description(uri)`             | `DESCRIBE` query for one entity                   |
| `entity_neighbours(uri, limit=10)`    | Outgoing + incoming relations                     |
| `entity_types(uri)`                   | All `rdf:type` values                             |
| `find_by_label(label, lang, limit)`   | Entities matching an `rdfs:label`                 |
| `predicates_of(uri)`                  | Predicates used by an entity, by frequency        |

**Graph Analytics**

| Function                          | Returns                                              |
|-----------------------------------|------------------------------------------------------|
| `top_entities_by_degree(limit)`   | Most connected nodes by total degree                 |
| `predicate_frequency()`           | Each predicate ranked by triple count                |
| `type_counts()`                   | Each `rdf:type` ranked by instance count             |
| `subgraph_sample(type_uri, limit)`| Sample entities of a given type                      |

**Wikidata-compatible patterns**

| Function                              | Returns                                           |
|---------------------------------------|---------------------------------------------------|
| `wikidata_entity(qid)`               | All direct statements for a QID                   |
| `wikidata_search(label, lang)`        | Entities by label in Wikidata conventions         |
| `wikidata_instanceof(class_qid, limit)` | Instances of a class via `wdt:P31`            |

---

## Examples

### Basic query

```python
from utils import QLeverClient

client = QLeverClient("http://localhost:7001")
rows = client.query_df("SELECT * WHERE { ?s ?p ?o } LIMIT 5")
for row in rows:
    print(row)
```

### Using templates

```python
from utils import QLeverClient, templates

client = QLeverClient("http://localhost:7001")

# Predicate frequency across the whole graph
sparql = templates.predicate_frequency()
rows = client.query_df(sparql)

# All rdf:type values for one entity
sparql = templates.entity_types("http://www.wikidata.org/entity/Q42")
rows = client.query_df(sparql)

# Wikidata: all humans (Q5)
sparql = templates.wikidata_instanceof("Q5", limit=20)
rows = client.query_df(sparql)
```

### Async batch queries

```python
import asyncio
from utils.async_client import AsyncQLeverClient
from utils import templates

async def main():
    async with AsyncQLeverClient("http://localhost:7001") as client:
        results = await client.batch_query([
            templates.predicate_frequency(),
            templates.type_counts(),
            templates.top_entities_by_degree(limit=10),
        ])
        for r in results:
            print(r)

asyncio.run(main())
```

### Full end-to-end demo

```bash
python examples/vision2030_demo.py http://localhost:7001
```

The demo runs five queries covering predicate frequency, type counts, degree
analytics, the fluent builder, and label-based entity lookup with neighbour
exploration.
