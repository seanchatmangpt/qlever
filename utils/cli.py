"""Command-line interface for QLever utilities.

Usage:
  python -m utils query <endpoint> <sparql>       Execute SPARQL SELECT
  python -m utils ask <endpoint> <sparql>         Execute ASK query
  python -m utils describe <endpoint> <uri>       DESCRIBE <uri>
  python -m utils triples <endpoint> <subject>    List all triples for subject
  python -m utils count <endpoint>                Count total triples
  python -m utils prefixes <prefix_file>          Parse & display prefix map
  python -m utils format <sparql_file>            Pretty-print a SPARQL file
"""
from __future__ import annotations

import argparse
import csv
import json
import io
import sys
from typing import Any, Dict, List, Optional

from .client import QLeverClient, QLeverError
from .rdf_utils import PrefixMap
from .sparql_builder import select, ask as ask_query, construct


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _print_table(rows: List[Dict[str, str]], columns: List[str]) -> None:
    """Print rows as an aligned table."""
    if not rows:
        print("(no results)")
        return

    # Compute column widths
    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            widths[col] = max(widths[col], len(row.get(col, "")))

    # Header
    header = "  ".join(col.ljust(widths[col]) for col in columns)
    separator = "  ".join("-" * widths[col] for col in columns)
    print(header)
    print(separator)
    for row in rows:
        line = "  ".join(row.get(col, "").ljust(widths[col]) for col in columns)
        print(line)


def _print_json(rows: List[Dict[str, str]], columns: List[str]) -> None:
    """Print rows as JSON array."""
    print(json.dumps(rows, indent=2, ensure_ascii=False))


def _print_csv(rows: List[Dict[str, str]], columns: List[str]) -> None:
    """Print rows as CSV."""
    writer = csv.DictWriter(sys.stdout, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({col: row.get(col, "") for col in columns})


def _print_tsv(rows: List[Dict[str, str]], columns: List[str]) -> None:
    """Print rows as TSV."""
    print("\t".join(columns))
    for row in rows:
        print("\t".join(row.get(col, "") for col in columns))


_FORMATTERS = {
    "table": _print_table,
    "json": _print_json,
    "csv": _print_csv,
    "tsv": _print_tsv,
}


def _output(rows: List[Dict[str, str]], columns: List[str], fmt: str) -> None:
    formatter = _FORMATTERS.get(fmt)
    if formatter is None:
        print(f"Unknown format: {fmt!r}", file=sys.stderr)
        sys.exit(1)
    formatter(rows, columns)


def _extract_columns(result: Dict[str, Any]) -> List[str]:
    """Extract variable names (columns) from a sparql_json_export result."""
    return result.get("head", {}).get("vars", [])


def _extract_rows(result: Dict[str, Any], columns: List[str]) -> List[Dict[str, str]]:
    """Extract rows from a sparql_json_export result."""
    bindings = result.get("results", {}).get("bindings", [])
    rows = []
    for binding in bindings:
        row = {col: binding[col]["value"] if col in binding else "" for col in columns}
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_query(args: argparse.Namespace) -> int:
    """Execute a SPARQL SELECT query and print results."""
    client = QLeverClient(args.endpoint)
    try:
        result = client.query(args.sparql, action="sparql_json_export")
    except QLeverError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not isinstance(result, dict):
        print(result)
        return 0

    columns = _extract_columns(result)
    rows = _extract_rows(result, columns)
    _output(rows, columns, args.format)
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    """Execute a SPARQL ASK query and print the boolean result."""
    client = QLeverClient(args.endpoint)
    try:
        result = client.query(args.sparql, action="sparql_json_export")
    except QLeverError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if isinstance(result, dict):
        answer = result.get("boolean")
        if answer is None:
            # Might be a SELECT wrapped as ASK; fall back to printing raw
            print(json.dumps(result, indent=2))
        else:
            if args.format == "json":
                print(json.dumps({"result": answer}, indent=2))
            else:
                print("true" if answer else "false")
    else:
        print(result)
    return 0


def cmd_describe(args: argparse.Namespace) -> int:
    """Execute a SPARQL DESCRIBE query for a URI and print triples."""
    uri = args.uri
    if not uri.startswith("<"):
        uri = f"<{uri}>"
    sparql = f"DESCRIBE {uri}"
    client = QLeverClient(args.endpoint)
    try:
        # Use turtle_export for DESCRIBE
        result = client.query(sparql, action="turtle_export")
    except QLeverError as e:
        # Fallback: try tsv_export with a CONSTRUCT
        try:
            construct_sparql = (
                f"CONSTRUCT {{ {uri} ?p ?o }} WHERE {{ {uri} ?p ?o }}"
            )
            result = client.query(construct_sparql, action="tsv_export")
        except QLeverError as e2:
            print(f"Error: {e2}", file=sys.stderr)
            return 1

    # result is a string (Turtle or TSV)
    if args.format == "json":
        print(json.dumps({"result": result}, indent=2))
    else:
        print(result)
    return 0


def cmd_triples(args: argparse.Namespace) -> int:
    """List all triples for a given subject."""
    subject = args.subject
    if not subject.startswith("<"):
        subject = f"<{subject}>"

    sparql = (
        f"SELECT ?predicate ?object WHERE {{ {subject} ?predicate ?object }}"
    )
    client = QLeverClient(args.endpoint)
    try:
        result = client.query(sparql, action="sparql_json_export")
    except QLeverError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not isinstance(result, dict):
        print(result)
        return 0

    columns = ["predicate", "object"]
    rows = _extract_rows(result, columns)

    # Prepend subject column for display
    display_columns = ["subject", "predicate", "object"]
    display_rows = [{"subject": args.subject, **row} for row in rows]
    _output(display_rows, display_columns, args.format)
    return 0


def cmd_count(args: argparse.Namespace) -> int:
    """Count total triples in the endpoint."""
    sparql = "SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }"
    client = QLeverClient(args.endpoint)
    try:
        result = client.query(sparql, action="sparql_json_export")
    except QLeverError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not isinstance(result, dict):
        print(result)
        return 0

    columns = _extract_columns(result)
    rows = _extract_rows(result, columns)

    if args.format == "json":
        # Extract the scalar value for cleaner JSON
        count_val = rows[0].get("count", "0") if rows else "0"
        print(json.dumps({"total_triples": int(count_val)}, indent=2))
    else:
        _output(rows, columns, args.format)
    return 0


def cmd_prefixes(args: argparse.Namespace) -> int:
    """Parse a prefix file and display the prefix map."""
    try:
        with open(args.prefix_file, "r", encoding="utf-8") as fh:
            content = fh.read()
    except OSError as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        return 1

    # Parse PREFIX declarations from SPARQL or Turtle-style prefix files
    import re
    prefix_pattern = re.compile(
        r'(?:PREFIX\s+)?(@?prefix\s+)?(\w*)\s*:\s*<([^>]+)>',
        re.IGNORECASE,
    )
    # Also handle simple "short: <full>" lines
    simple_pattern = re.compile(r'^(\w+)\s*:\s*<([^>]+)>', re.MULTILINE)

    found: Dict[str, str] = {}

    # Try SPARQL PREFIX keyword first
    for m in re.finditer(r'PREFIX\s+(\w*)\s*:\s*<([^>]+)>', content, re.IGNORECASE):
        found[m.group(1)] = m.group(2)

    # Try Turtle @prefix
    for m in re.finditer(r'@prefix\s+(\w*)\s*:\s*<([^>]+)>', content, re.IGNORECASE):
        found[m.group(1)] = m.group(2)

    # Try simple "key: <value>" lines (e.g., .prefixes config files)
    if not found:
        for m in simple_pattern.finditer(content):
            found[m.group(1)] = m.group(2)

    if not found:
        print("No prefixes found in file.", file=sys.stderr)
        return 1

    rows = [{"prefix": k, "iri": v} for k, v in sorted(found.items())]
    columns = ["prefix", "iri"]

    if args.format == "json":
        _print_json(rows, columns)
    elif args.format == "csv":
        _print_csv(rows, columns)
    elif args.format == "tsv":
        _print_tsv(rows, columns)
    else:
        _print_table(rows, columns)

    return 0


def cmd_format(args: argparse.Namespace) -> int:
    """Pretty-print a SPARQL file."""
    try:
        with open(args.sparql_file, "r", encoding="utf-8") as fh:
            content = fh.read()
    except OSError as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        return 1

    formatted = _format_sparql(content)

    if args.format == "json":
        print(json.dumps({"formatted": formatted}, indent=2))
    else:
        print(formatted)
    return 0


def _format_sparql(sparql: str) -> str:
    """Pretty-print a SPARQL query string."""
    import re

    # Normalise whitespace
    text = sparql.strip()

    # Keywords to place on their own line (preceded by newline)
    top_level_kw = re.compile(
        r'\b(PREFIX|SELECT|DISTINCT|ASK|CONSTRUCT|DESCRIBE|WHERE|GROUP\s+BY|'
        r'HAVING|ORDER\s+BY|LIMIT|OFFSET|FROM|NAMED|OPTIONAL|UNION|FILTER|'
        r'MINUS|SERVICE|GRAPH|VALUES|BIND)\b',
        re.IGNORECASE,
    )

    lines = []
    indent = 0
    # Split on { and } to maintain brace structure
    tokens = re.split(r'(\{|\})', text)

    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if token == '{':
            lines.append(' ' * (indent * 2) + '{')
            indent += 1
        elif token == '}':
            indent = max(0, indent - 1)
            lines.append(' ' * (indent * 2) + '}')
        else:
            # Break on top-level keywords within this fragment
            sub = top_level_kw.sub(r'\n\1', token)
            for sub_line in sub.splitlines():
                sub_line = sub_line.strip()
                if sub_line:
                    lines.append(' ' * (indent * 2) + sub_line)

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m utils",
        description="QLever command-line utilities for SPARQL and RDF operations.",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json", "csv", "tsv"],
        default="table",
        help="Output format (default: table)",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # query
    p_query = sub.add_parser("query", help="Execute a SPARQL SELECT query")
    p_query.add_argument("endpoint", help="QLever endpoint URL")
    p_query.add_argument("sparql", help="SPARQL SELECT query string")
    p_query.set_defaults(func=cmd_query)

    # ask
    p_ask = sub.add_parser("ask", help="Execute a SPARQL ASK query")
    p_ask.add_argument("endpoint", help="QLever endpoint URL")
    p_ask.add_argument("sparql", help="SPARQL ASK query string")
    p_ask.set_defaults(func=cmd_ask)

    # describe
    p_describe = sub.add_parser("describe", help="DESCRIBE a URI")
    p_describe.add_argument("endpoint", help="QLever endpoint URL")
    p_describe.add_argument("uri", help="URI to describe (angle brackets optional)")
    p_describe.set_defaults(func=cmd_describe)

    # triples
    p_triples = sub.add_parser(
        "triples", help="List all triples for a given subject"
    )
    p_triples.add_argument("endpoint", help="QLever endpoint URL")
    p_triples.add_argument(
        "subject", help="Subject URI (angle brackets optional)"
    )
    p_triples.set_defaults(func=cmd_triples)

    # count
    p_count = sub.add_parser("count", help="Count total triples in the endpoint")
    p_count.add_argument("endpoint", help="QLever endpoint URL")
    p_count.set_defaults(func=cmd_count)

    # prefixes
    p_prefixes = sub.add_parser(
        "prefixes", help="Parse and display prefixes from a file"
    )
    p_prefixes.add_argument(
        "prefix_file",
        help="Path to a file with PREFIX declarations (SPARQL, Turtle, or simple)",
    )
    p_prefixes.set_defaults(func=cmd_prefixes)

    # format
    p_format = sub.add_parser("format", help="Pretty-print a SPARQL file")
    p_format.add_argument("sparql_file", help="Path to a SPARQL file")
    p_format.set_defaults(func=cmd_format)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> None:
    """Main entry point for the QLever CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Propagate --format to subcommand namespace (it lives on the top parser)
    # argparse already merges it into args because it's defined on the root parser.
    rc = args.func(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
