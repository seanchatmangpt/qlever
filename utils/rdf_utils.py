"""RDF data helpers: IRI formatting, literals, prefix management, N-Triples parsing."""
from __future__ import annotations

import re
from typing import Dict, Optional, Tuple, List


class PrefixMap:
    """Manages namespace prefix-to-IRI mappings for SPARQL and RDF."""

    COMMON_PREFIXES = {
        'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
        'rdfs': 'http://www.w3.org/2000/01/rdf-schema#',
        'xsd': 'http://www.w3.org/2001/XMLSchema#',
        'owl': 'http://www.w3.org/2002/07/owl#',
        'schema': 'https://schema.org/',
        'wd': 'http://www.wikidata.org/entity/',
        'wdt': 'http://www.wikidata.org/prop/direct/',
    }

    def __init__(self, include_common: bool = True, **prefixes: str):
        self._prefixes: Dict[str, str] = {}
        if include_common:
            self._prefixes.update(self.COMMON_PREFIXES)
        self._prefixes.update(prefixes)

    def add(self, short: str, full_iri: str) -> None:
        """Add a prefix mapping."""
        self._prefixes[short] = full_iri

    def expand(self, prefixed: str) -> str:
        """Expand a prefixed name like 'rdf:type' to '<http://...#type>'."""
        if ':' not in prefixed or prefixed.startswith('<'):
            return prefixed
        prefix, local = prefixed.split(':', 1)
        if prefix in self._prefixes:
            return '<' + self._prefixes[prefix] + local + '>'
        return prefixed

    def shorten(self, full_iri: str) -> str:
        """Shorten a full IRI to prefixed form if a matching prefix exists."""
        # Strip angle brackets if present
        iri_str = full_iri
        if iri_str.startswith('<') and iri_str.endswith('>'):
            iri_str = iri_str[1:-1]
        for short, full in self._prefixes.items():
            if iri_str.startswith(full):
                return short + ':' + iri_str[len(full):]
        return full_iri

    def to_sparql_prefixes(self) -> str:
        """Return all prefixes as SPARQL PREFIX declarations."""
        lines = []
        for short, full in sorted(self._prefixes.items()):
            lines.append(f'PREFIX {short}: <{full}>')
        return '\n'.join(lines)

    def __contains__(self, key: str) -> bool:
        return key in self._prefixes

    def __len__(self) -> int:
        return len(self._prefixes)


def iri(value: str) -> str:
    """Wrap a string in angle brackets to form an IRI. No-op if already wrapped."""
    if value.startswith('<') and value.endswith('>'):
        return value
    return '<' + value + '>'


def literal(value: str, lang: Optional[str] = None,
            datatype: Optional[str] = None) -> str:
    """Create an RDF literal string with optional language tag or datatype."""
    if lang and datatype:
        raise ValueError("Cannot specify both lang and datatype for a literal")
    escaped = escape_sparql_string(value)
    result = '"' + escaped + '"'
    if lang:
        result += '@' + lang
    elif datatype:
        if not datatype.startswith('<'):
            datatype = '<' + datatype + '>'
        result += '^^' + datatype
    return result


def escape_sparql_string(value: str) -> str:
    """Escape special characters in a string for use in SPARQL."""
    value = value.replace('\\', '\\\\')
    value = value.replace('"', '\\"')
    value = value.replace('\n', '\\n')
    value = value.replace('\r', '\\r')
    value = value.replace('\t', '\\t')
    return value


# Regex for parsing N-Triples components
_IRI_PATTERN = r'<([^>]*)>'
_LITERAL_PATTERN = r'"((?:[^"\\]|\\.)*)"(?:@([a-zA-Z-]+)|\^\^<([^>]*)>)?'
_BNODE_PATTERN = r'(_:\S+)'
_TERM_PATTERN = f'(?:{_IRI_PATTERN}|{_LITERAL_PATTERN}|{_BNODE_PATTERN})'
_NT_LINE_RE = re.compile(
    rf'^\s*{_TERM_PATTERN}\s+{_TERM_PATTERN}\s+{_TERM_PATTERN}\s*\.\s*$'
)


def _extract_term(groups: tuple, offset: int) -> Optional[str]:
    """Extract an RDF term from regex match groups at the given offset."""
    iri_val = groups[offset]
    lit_val = groups[offset + 1]
    lit_lang = groups[offset + 2]
    lit_dt = groups[offset + 3]
    bnode = groups[offset + 4]

    if iri_val is not None:
        return '<' + iri_val + '>'
    elif lit_val is not None:
        result = '"' + lit_val + '"'
        if lit_lang:
            result += '@' + lit_lang
        elif lit_dt:
            result += '^^<' + lit_dt + '>'
        return result
    elif bnode is not None:
        return bnode
    return None


def parse_ntriples_line(line: str) -> Optional[Tuple[str, str, str]]:
    """Parse a single N-Triples line into (subject, predicate, object).

    Returns None for blank lines and comments.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        return None
    m = _NT_LINE_RE.match(stripped)
    if not m:
        return None
    groups = m.groups()
    s = _extract_term(groups, 0)
    p = _extract_term(groups, 5)
    o = _extract_term(groups, 10)
    if s and p and o:
        return (s, p, o)
    return None


def parse_ntriples(text: str) -> List[Tuple[str, str, str]]:
    """Parse multiple N-Triples lines into a list of (s, p, o) tuples."""
    results = []
    for line in text.splitlines():
        parsed = parse_ntriples_line(line)
        if parsed is not None:
            results.append(parsed)
    return results
