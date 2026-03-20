"""SPARQL query builder with a fluent API for SELECT, ASK, and CONSTRUCT queries."""
from __future__ import annotations

from typing import List, Optional


class SPARQLQuery:
    """Represents a SPARQL query built via a fluent interface."""

    def __init__(self, query_type: str, variables: Optional[List[str]] = None,
                 construct_template: Optional[str] = None):
        self._query_type = query_type
        self._variables = variables or []
        self._construct_template = construct_template
        self._distinct = False
        self._prefixes: List[tuple] = []
        self._where_clauses: List[str] = []
        self._filters: List[str] = []
        self._group_by: Optional[str] = None
        self._having: Optional[str] = None
        self._order_by: Optional[str] = None
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None

    def distinct(self) -> SPARQLQuery:
        """Add DISTINCT modifier to SELECT."""
        self._distinct = True
        return self

    def prefix(self, short: str, full_iri: str) -> SPARQLQuery:
        """Add a PREFIX declaration."""
        self._prefixes.append((short, full_iri))
        return self

    def where(self, pattern: str) -> SPARQLQuery:
        """Add a WHERE clause pattern."""
        self._where_clauses.append(pattern)
        return self

    def filter(self, expression: str) -> SPARQLQuery:
        """Add a FILTER expression."""
        self._filters.append(expression)
        return self

    def group_by(self, expression: str) -> SPARQLQuery:
        """Add a GROUP BY clause."""
        self._group_by = expression
        return self

    def having(self, expression: str) -> SPARQLQuery:
        """Add a HAVING clause."""
        self._having = expression
        return self

    def order_by(self, expression: str) -> SPARQLQuery:
        """Add an ORDER BY clause."""
        self._order_by = expression
        return self

    def limit(self, n: int) -> SPARQLQuery:
        """Set the LIMIT."""
        self._limit = n
        return self

    def offset(self, n: int) -> SPARQLQuery:
        """Set the OFFSET."""
        self._offset = n
        return self

    def build(self) -> str:
        """Build and return the SPARQL query string."""
        parts = []

        # Prefixes
        for short, full_iri in self._prefixes:
            parts.append(f'PREFIX {short}: <{full_iri}>')

        # Query form
        if self._query_type == 'SELECT':
            distinct = 'DISTINCT ' if self._distinct else ''
            vars_str = ' '.join(self._variables)
            parts.append(f'SELECT {distinct}{vars_str}')
        elif self._query_type == 'ASK':
            parts.append('ASK')
        elif self._query_type == 'CONSTRUCT':
            parts.append(f'CONSTRUCT {{ {self._construct_template} }}')

        # WHERE block
        body_lines = list(self._where_clauses)
        for f in self._filters:
            body_lines.append(f'FILTER({f})')
        body = '\n  '.join(body_lines)
        parts.append(f'WHERE {{\n  {body}\n}}')

        # Solution modifiers
        if self._group_by:
            parts.append(f'GROUP BY {self._group_by}')
        if self._having:
            parts.append(f'HAVING({self._having})')
        if self._order_by:
            parts.append(f'ORDER BY {self._order_by}')
        if self._offset is not None:
            parts.append(f'OFFSET {self._offset}')
        if self._limit is not None:
            parts.append(f'LIMIT {self._limit}')

        return '\n'.join(parts)


def select(*variables: str) -> SPARQLQuery:
    """Create a SELECT query with the given variables."""
    return SPARQLQuery('SELECT', list(variables))


def ask() -> SPARQLQuery:
    """Create an ASK query."""
    return SPARQLQuery('ASK')


def construct(template: str) -> SPARQLQuery:
    """Create a CONSTRUCT query with the given template."""
    return SPARQLQuery('CONSTRUCT', construct_template=template)


def _triples_to_str(triples: list) -> str:
    """Convert a list of (subject, predicate, object) tuples to triple statements."""
    lines = []
    for triple in triples:
        if len(triple) != 3:
            raise ValueError(f"Each triple must have exactly 3 elements, got {len(triple)}")
        s, p, o = triple
        lines.append(f'  {s} {p} {o} .')
    return '\n'.join(lines)


def insert_data(triples: list) -> str:
    """Generate a SPARQL INSERT DATA statement.

    Args:
        triples: List of (subject, predicate, object) tuples.

    Returns:
        A SPARQL INSERT DATA { ... } string.
    """
    body = _triples_to_str(triples)
    return f'INSERT DATA {{\n{body}\n}}'


def delete_data(triples: list) -> str:
    """Generate a SPARQL DELETE DATA statement.

    Args:
        triples: List of (subject, predicate, object) tuples.

    Returns:
        A SPARQL DELETE DATA { ... } string.
    """
    body = _triples_to_str(triples)
    return f'DELETE DATA {{\n{body}\n}}'


def update(delete_pattern: str, insert_pattern: str, where: str) -> str:
    """Generate a SPARQL DELETE/INSERT/WHERE update operation.

    Args:
        delete_pattern: Triple patterns for the DELETE clause.
        insert_pattern: Triple patterns for the INSERT clause.
        where: Graph pattern for the WHERE clause.

    Returns:
        A SPARQL DELETE { ... } INSERT { ... } WHERE { ... } string.
    """
    return (
        f'DELETE {{\n  {delete_pattern}\n}}\n'
        f'INSERT {{\n  {insert_pattern}\n}}\n'
        f'WHERE {{\n  {where}\n}}'
    )


def values_block(var_names: list, rows: list) -> str:
    """Generate a SPARQL VALUES block.

    Args:
        var_names: List of variable names (without leading '?').
        rows: List of value rows; each row is a list of RDF terms matching var_names.

    Returns:
        A SPARQL VALUES (?x ?y) { ... } block string.
    """
    vars_str = ' '.join(f'?{v}' for v in var_names)
    row_lines = []
    for row in rows:
        if len(row) != len(var_names):
            raise ValueError(
                f"Row length {len(row)} does not match number of variables {len(var_names)}"
            )
        row_str = ' '.join(str(val) for val in row)
        row_lines.append(f'  ( {row_str} )')
    body = '\n'.join(row_lines)
    return f'VALUES ({vars_str}) {{\n{body}\n}}'


def service_clause(endpoint: str, pattern: str) -> str:
    """Generate a SPARQL SERVICE clause for federated queries.

    Args:
        endpoint: The remote SPARQL endpoint IRI (with or without angle brackets).
        pattern: The graph pattern to evaluate at the remote endpoint.

    Returns:
        A SPARQL SERVICE <endpoint> { pattern } string.
    """
    if not endpoint.startswith('<'):
        endpoint = f'<{endpoint}>'
    return f'SERVICE {endpoint} {{\n  {pattern}\n}}'


class GraphManager:
    """Utilities for managing named graphs in SPARQL."""

    def named_graph_query(self, graph_uri: str, sparql_body: str) -> str:
        """Wrap a SPARQL graph pattern inside a GRAPH { } clause.

        Args:
            graph_uri: The named graph IRI (with or without angle brackets).
            sparql_body: The SPARQL pattern to wrap.

        Returns:
            A GRAPH <graph_uri> { sparql_body } string.
        """
        if not graph_uri.startswith('<'):
            graph_uri = f'<{graph_uri}>'
        return f'GRAPH {graph_uri} {{\n  {sparql_body}\n}}'

    def copy_graph(self, src: str, dst: str) -> str:
        """Generate a SPARQL COPY GRAPH statement.

        Args:
            src: Source named graph IRI (with or without angle brackets).
            dst: Destination named graph IRI (with or without angle brackets).

        Returns:
            A SPARQL COPY <src> TO <dst> string.
        """
        if not src.startswith('<'):
            src = f'<{src}>'
        if not dst.startswith('<'):
            dst = f'<{dst}>'
        return f'COPY {src} TO {dst}'

    def drop_graph(self, graph_uri: str) -> str:
        """Generate a SPARQL DROP GRAPH IF EXISTS statement.

        Args:
            graph_uri: The named graph IRI to drop (with or without angle brackets).

        Returns:
            A SPARQL DROP GRAPH IF EXISTS <graph_uri> string.
        """
        if not graph_uri.startswith('<'):
            graph_uri = f'<{graph_uri}>'
        return f'DROP GRAPH IF EXISTS {graph_uri}'
