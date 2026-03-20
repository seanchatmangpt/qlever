"""Vision 2030 QLever Demo — end-to-end demonstration of the utils package.

This module shows how to use QLeverClient, the fluent select() builder,
PrefixMap, and the templates library together in a realistic workflow.

Run from the repository root::

    python examples/vision2030_demo.py                        # default localhost:7001
    python examples/vision2030_demo.py http://my-server:7001  # custom endpoint

All queries are executed with graceful error handling so the script is safe
to run even when no QLever endpoint is reachable.
"""
from __future__ import annotations

import sys
import textwrap
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Import from the utils package (one level up when run from the repo root)
# ---------------------------------------------------------------------------
try:
    import utils
    from utils import QLeverClient, QLeverError, PrefixMap, select
    from utils import templates
except ModuleNotFoundError:
    # Allow running the script from inside the examples/ directory
    sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))
    import utils
    from utils import QLeverClient, QLeverError, PrefixMap, select
    from utils import templates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    """Print a clearly visible section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def _run_query(
    client: QLeverClient,
    description: str,
    sparql: str,
    max_rows: int = 5,
) -> List[Dict[str, Any]]:
    """Execute *sparql*, print up to *max_rows* result rows, return all rows.

    Returns an empty list on error instead of propagating the exception, so
    the demo continues even when individual queries fail or the endpoint is
    unavailable.
    """
    print(f"\n[Query] {description}")
    print(textwrap.indent(sparql.strip(), "  "))
    print()
    try:
        rows = client.query_df(sparql)
        if not rows:
            print("  (no results)")
            return rows
        for i, row in enumerate(rows[:max_rows]):
            print(f"  row {i + 1}: {row}")
        if len(rows) > max_rows:
            print(f"  ... ({len(rows) - max_rows} more rows not shown)")
        return rows
    except QLeverError as exc:
        print(f"  [QLeverError] {exc}")
        return []
    except Exception as exc:  # noqa: BLE001
        print(f"  [Error] {type(exc).__name__}: {exc}")
        return []


# ---------------------------------------------------------------------------
# Demo queries
# ---------------------------------------------------------------------------

def _demo_predicate_frequency(client: QLeverClient) -> None:
    """Demo 1 — Graph-level analytics: predicate frequency."""
    _section("Demo 1: Predicate frequency across the whole graph")
    sparql = templates.predicate_frequency()
    _run_query(client, "Most-used predicates", sparql)


def _demo_type_counts(client: QLeverClient) -> None:
    """Demo 2 — Graph-level analytics: instance counts per type."""
    _section("Demo 2: Instance counts per rdf:type")
    sparql = templates.type_counts()
    _run_query(client, "Types ranked by entity count", sparql)


def _demo_top_entities(client: QLeverClient) -> None:
    """Demo 3 — Graph analytics: most connected nodes."""
    _section("Demo 3: Top entities by degree (most connected nodes)")
    sparql = templates.top_entities_by_degree(limit=10)
    _run_query(client, "Top-10 entities by total degree", sparql)


def _demo_fluent_builder(client: QLeverClient) -> None:
    """Demo 4 — Fluent query builder + PrefixMap for a custom SELECT."""
    _section("Demo 4: Fluent SELECT builder with PrefixMap")

    pm = PrefixMap(include_common=True)

    # Build a query that finds entities with an English label and counts their
    # outgoing triples, ordered by connectivity.
    sparql = (
        select("?entity", "?label", "(COUNT(?p) AS ?degree)")
        .prefix("rdf",  pm._prefixes["rdf"])
        .prefix("rdfs", pm._prefixes["rdfs"])
        .where("?entity rdfs:label ?label .")
        .where("?entity ?p ?o .")
        .filter('LANG(?label) = "en"')
        .group_by("?entity ?label")
        .order_by("DESC(?degree)")
        .limit(10)
        .build()
    )
    _run_query(client, "Top-10 labelled entities by outgoing degree", sparql)


def _demo_find_by_label(client: QLeverClient) -> None:
    """Demo 5 — Template: find entities by label."""
    _section("Demo 5: Find entities by English rdfs:label")

    # Try a few common labels that might appear in a generic knowledge graph
    for label in ("Germany", "France", "Berlin"):
        sparql = templates.find_by_label(label, lang="en", limit=5)
        rows = _run_query(
            client,
            f'Entities labelled "{label}"@en',
            sparql,
            max_rows=3,
        )
        if rows:
            # Once we find results, demonstrate entity_neighbours on the first hit
            first_entity = rows[0].get("entity", "")
            if first_entity:
                _section(f"  Bonus: neighbours of <{first_entity}>")
                nb_sparql = templates.entity_neighbours(first_entity, limit=6)
                _run_query(
                    client,
                    f"Neighbours of first result entity",
                    nb_sparql,
                    max_rows=6,
                )
            break


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def demo(endpoint_url: str = "http://localhost:7001") -> None:
    """Run all five demonstration queries against *endpoint_url*.

    Args:
        endpoint_url: Base URL of a running QLever SPARQL endpoint.
                      Defaults to ``http://localhost:7001``.
    """
    print(f"\nQLever Vision 2030 Demo")
    print(f"Endpoint : {endpoint_url}")
    print(f"utils    : v{utils.__version__}")

    client = QLeverClient(endpoint_url, timeout=15.0)

    # Check connectivity before running the full suite
    _section("Connectivity check")
    try:
        stats = client.stats()
        index_name = stats.get("index-builder-settings", {}).get("name-of-index",
                    stats.get("name-of-index", "<unknown>"))
        print(f"  Connected — index: {index_name}")
    except QLeverError as exc:
        print(f"  Could not reach endpoint: {exc}")
        print("  Continuing anyway — individual queries will report their own errors.")
    except Exception as exc:  # noqa: BLE001
        print(f"  Unexpected error during connectivity check: {exc}")

    # Run the five demos
    _demo_predicate_frequency(client)
    _demo_type_counts(client)
    _demo_top_entities(client)
    _demo_fluent_builder(client)
    _demo_find_by_label(client)

    _section("Demo complete")
    print("  All five demonstrations finished.")
    print("  Re-run with a different endpoint URL as the first argument.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _endpoint = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:7001"
    demo(_endpoint)
