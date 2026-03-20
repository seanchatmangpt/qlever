"""QLever Python utilities for SPARQL querying and RDF data handling."""
from __future__ import annotations

__version__ = "0.1.0"

from .client import QLeverClient, QLeverError
from .rdf_utils import PrefixMap, escape_sparql_string, iri, literal, parse_ntriples, parse_ntriples_line
from .sparql_builder import (
    SPARQLQuery,
    ask,
    construct,
    delete_data,
    GraphManager,
    insert_data,
    select,
    service_clause,
    update,
    values_block,
)

__all__ = [
    'QLeverClient',
    'QLeverError',
    'PrefixMap',
    'SPARQLQuery',
    'ask',
    'construct',
    'delete_data',
    'escape_sparql_string',
    'GraphManager',
    'insert_data',
    'iri',
    'literal',
    'parse_ntriples',
    'parse_ntriples_line',
    'select',
    'service_clause',
    'update',
    'values_block',
]
