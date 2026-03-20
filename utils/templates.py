"""Pre-built SPARQL query templates for common knowledge graph patterns."""
from __future__ import annotations

from .rdf_utils import escape_sparql_string

# ---------------------------------------------------------------------------
# Standard prefix block used by all templates
# ---------------------------------------------------------------------------

_COMMON_PREFIXES = """\
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>"""

_WIKIDATA_PREFIXES = """\
PREFIX wd:   <http://www.wikidata.org/entity/>
PREFIX wdt:  <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>"""


def _wrap_iri(uri: str) -> str:
    """Return *uri* wrapped in angle brackets if not already wrapped."""
    if uri.startswith('<') and uri.endswith('>'):
        return uri
    return f'<{uri}>'


# ===========================================================================
# Knowledge Graph Exploration
# ===========================================================================

def entity_description(uri: str) -> str:
    """Return a SPARQL DESCRIBE query for a single entity.

    Args:
        uri: The full IRI of the entity (angle brackets are added if absent).

    Returns:
        A SPARQL DESCRIBE query string.
    """
    node = _wrap_iri(uri)
    return f"{_COMMON_PREFIXES}\nDESCRIBE {node}"


def entity_neighbours(uri: str, limit: int = 10) -> str:
    """Return a SELECT query for all outgoing and incoming relations of an entity.

    The result has columns ``?direction``, ``?predicate``, and ``?neighbour``.
    Outgoing triples (where the entity is the subject) are labelled
    ``"outgoing"``; incoming triples (where the entity is the object) are
    labelled ``"incoming"``.

    Args:
        uri:   The full IRI of the entity.
        limit: Maximum number of result rows (default 10).

    Returns:
        A SPARQL SELECT query string.
    """
    node = _wrap_iri(uri)
    return f"""{_COMMON_PREFIXES}
SELECT ?direction ?predicate ?neighbour
WHERE {{
  {{
    {node} ?predicate ?neighbour .
    BIND("outgoing" AS ?direction)
  }}
  UNION
  {{
    ?neighbour ?predicate {node} .
    BIND("incoming" AS ?direction)
  }}
}}
LIMIT {limit}"""


def entity_types(uri: str) -> str:
    """Return a SELECT query for all rdf:type values of an entity.

    Args:
        uri: The full IRI of the entity.

    Returns:
        A SPARQL SELECT query string with a single ``?type`` column.
    """
    node = _wrap_iri(uri)
    return f"""{_COMMON_PREFIXES}
SELECT DISTINCT ?type
WHERE {{
  {node} rdf:type ?type .
}}
ORDER BY ?type"""


def find_by_label(label: str, lang: str = "en", limit: int = 10) -> str:
    """Return a SELECT query that searches for entities by rdfs:label.

    Args:
        label: The label text to search for (case-sensitive exact match).
        lang:  BCP-47 language tag for the label literal (default ``"en"``).
        limit: Maximum number of result rows (default 10).

    Returns:
        A SPARQL SELECT query string with ``?entity`` and ``?label`` columns.
    """
    safe_label = escape_sparql_string(label)
    return f"""{_COMMON_PREFIXES}
SELECT DISTINCT ?entity ?label
WHERE {{
  ?entity rdfs:label ?label .
  FILTER(?label = "{safe_label}"@{lang})
}}
LIMIT {limit}"""


def predicates_of(uri: str) -> str:
    """Return a SELECT query listing every predicate used by an entity.

    Only outgoing triples (the entity as subject) are considered.

    Args:
        uri: The full IRI of the entity.

    Returns:
        A SPARQL SELECT query string with ``?predicate`` and ``?uses`` columns,
        ordered by descending usage count.
    """
    node = _wrap_iri(uri)
    return f"""{_COMMON_PREFIXES}
SELECT ?predicate (COUNT(*) AS ?uses)
WHERE {{
  {node} ?predicate ?object .
}}
GROUP BY ?predicate
ORDER BY DESC(?uses)"""


# ===========================================================================
# Graph Analytics
# ===========================================================================

def top_entities_by_degree(limit: int = 20) -> str:
    """Return a SELECT query ranking entities by total degree (in + out edges).

    Args:
        limit: Number of top entities to return (default 20).

    Returns:
        A SPARQL SELECT query string with ``?entity`` and ``?degree`` columns,
        ordered by descending degree.
    """
    return f"""{_COMMON_PREFIXES}
SELECT ?entity (COUNT(*) AS ?degree)
WHERE {{
  {{
    ?entity ?p ?o .
  }}
  UNION
  {{
    ?s ?p ?entity .
    FILTER(isIRI(?entity))
  }}
}}
GROUP BY ?entity
ORDER BY DESC(?degree)
LIMIT {limit}"""


def predicate_frequency() -> str:
    """Return a SELECT query counting how often each predicate is used.

    Returns:
        A SPARQL SELECT query string with ``?predicate`` and ``?triples``
        columns, ordered by descending triple count.
    """
    return f"""{_COMMON_PREFIXES}
SELECT ?predicate (COUNT(*) AS ?triples)
WHERE {{
  ?s ?predicate ?o .
}}
GROUP BY ?predicate
ORDER BY DESC(?triples)"""


def type_counts() -> str:
    """Return a SELECT query counting instances per rdf:type.

    Returns:
        A SPARQL SELECT query string with ``?type`` and ``?instances`` columns,
        ordered by descending instance count.
    """
    return f"""{_COMMON_PREFIXES}
SELECT ?type (COUNT(DISTINCT ?entity) AS ?instances)
WHERE {{
  ?entity rdf:type ?type .
}}
GROUP BY ?type
ORDER BY DESC(?instances)"""


def subgraph_sample(type_uri: str, limit: int = 100) -> str:
    """Return a SELECT query sampling entities of a given rdf:type.

    Args:
        type_uri: The full IRI of the type class.
        limit:    Maximum number of entities to return (default 100).

    Returns:
        A SPARQL SELECT query string with ``?entity`` and optional ``?label``
        columns.
    """
    type_node = _wrap_iri(type_uri)
    return f"""{_COMMON_PREFIXES}
SELECT DISTINCT ?entity ?label
WHERE {{
  ?entity rdf:type {type_node} .
  OPTIONAL {{ ?entity rdfs:label ?label . FILTER(LANG(?label) = "en") }}
}}
LIMIT {limit}"""


# ===========================================================================
# Wikidata-compatible patterns
# ===========================================================================

def wikidata_entity(qid: str) -> str:
    """Return a SELECT query retrieving all direct statements for a Wikidata QID.

    The QID may be supplied with or without the ``Q`` prefix (e.g. ``"Q42"``
    or the full IRI ``"http://www.wikidata.org/entity/Q42"``).

    Args:
        qid: Wikidata entity identifier (e.g. ``"Q42"``).

    Returns:
        A SPARQL SELECT query string with ``?property`` and ``?value`` columns.
    """
    # Accept plain QIDs like "Q42" or full IRIs
    if qid.startswith('http') or qid.startswith('<'):
        entity_term = _wrap_iri(qid)
    elif qid.startswith('wd:'):
        entity_term = qid
    else:
        entity_term = f'wd:{qid}'
    return f"""{_WIKIDATA_PREFIXES}
SELECT ?property ?value
WHERE {{
  {entity_term} ?property ?value .
}}
ORDER BY ?property"""


def wikidata_search(label: str, lang: str = "en") -> str:
    """Return a SELECT query searching Wikidata entities by rdfs:label.

    Args:
        label: Label text to match exactly.
        lang:  BCP-47 language tag (default ``"en"``).

    Returns:
        A SPARQL SELECT query string with ``?entity``, ``?label``, and
        ``?description`` columns.
    """
    safe_label = escape_sparql_string(label)
    return f"""{_WIKIDATA_PREFIXES}
SELECT DISTINCT ?entity ?label ?description
WHERE {{
  ?entity rdfs:label "{safe_label}"@{lang} .
  BIND("{safe_label}"@{lang} AS ?label)
  OPTIONAL {{
    ?entity <http://schema.org/description> ?description .
    FILTER(LANG(?description) = "{lang}")
  }}
}}
LIMIT 20"""


def wikidata_instanceof(class_qid: str, limit: int = 50) -> str:
    """Return a SELECT query for all instances of a Wikidata class (P31).

    Args:
        class_qid: Wikidata class QID (e.g. ``"Q5"`` for human).
        limit:     Maximum number of instances to return (default 50).

    Returns:
        A SPARQL SELECT query string with ``?entity`` and ``?label`` columns.
    """
    if class_qid.startswith('http') or class_qid.startswith('<'):
        class_term = _wrap_iri(class_qid)
    elif class_qid.startswith('wd:'):
        class_term = class_qid
    else:
        class_term = f'wd:{class_qid}'
    return f"""{_WIKIDATA_PREFIXES}
SELECT DISTINCT ?entity ?label
WHERE {{
  ?entity wdt:P31 {class_term} .
  OPTIONAL {{ ?entity rdfs:label ?label . FILTER(LANG(?label) = "en") }}
}}
LIMIT {limit}"""
