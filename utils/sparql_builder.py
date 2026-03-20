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
