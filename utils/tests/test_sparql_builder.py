"""Tests for utils.sparql_builder: select, ask, construct, SPARQLQuery fluent builder."""
from __future__ import annotations

import pytest

from utils.sparql_builder import SPARQLQuery, ask, construct, select


# ---------------------------------------------------------------------------
# select()
# ---------------------------------------------------------------------------

class TestSelect:
    def test_basic_select(self):
        q = select("?s", "?p", "?o").where("?s ?p ?o").build()
        assert "SELECT ?s ?p ?o" in q
        assert "WHERE {" in q

    def test_select_star(self):
        q = select("*").where("?s ?p ?o").build()
        assert "SELECT *" in q

    def test_select_distinct(self):
        q = select("?s").distinct().where("?s ?p ?o").build()
        assert "SELECT DISTINCT ?s" in q

    def test_select_order_by(self):
        q = select("?s").where("?s ?p ?o").order_by("?s").build()
        assert "ORDER BY ?s" in q

    def test_select_limit(self):
        q = select("?s").where("?s ?p ?o").limit(10).build()
        assert "LIMIT 10" in q

    def test_select_offset(self):
        q = select("?s").where("?s ?p ?o").offset(20).build()
        assert "OFFSET 20" in q

    def test_select_limit_and_offset(self):
        q = select("?s").where("?s ?p ?o").limit(10).offset(5).build()
        assert "LIMIT 10" in q
        assert "OFFSET 5" in q

    def test_select_no_distinct_by_default(self):
        q = select("?s").where("?s ?p ?o").build()
        assert "DISTINCT" not in q

    def test_select_multiple_where_clauses(self):
        q = (
            select("?s", "?label")
            .where("?s a <http://example.org/Person>")
            .where("?s <http://example.org/name> ?label")
            .build()
        )
        assert "?s a <http://example.org/Person>" in q
        assert "?s <http://example.org/name> ?label" in q

    def test_select_filter(self):
        q = select("?s").where("?s ?p ?o").filter("?o > 5").build()
        assert "FILTER(?o > 5)" in q


# ---------------------------------------------------------------------------
# ask()
# ---------------------------------------------------------------------------

class TestAsk:
    def test_ask_basic(self):
        q = ask().where("?s ?p ?o").build()
        assert q.startswith("ASK") or "ASK" in q
        assert "WHERE {" in q

    def test_ask_with_pattern(self):
        q = ask().where("<http://a.org/s> <http://a.org/p> <http://a.org/o>").build()
        assert "<http://a.org/s>" in q


# ---------------------------------------------------------------------------
# construct()
# ---------------------------------------------------------------------------

class TestConstruct:
    def test_construct_basic(self):
        tmpl = "?s <http://example.org/p> ?o"
        q = construct(tmpl).where("?s ?p ?o").build()
        assert "CONSTRUCT {" in q
        assert tmpl in q
        assert "WHERE {" in q

    def test_construct_with_filter(self):
        q = (
            construct("?s <http://example.org/p> ?o")
            .where("?s ?p ?o")
            .filter("?o > 0")
            .build()
        )
        assert "FILTER(?o > 0)" in q


# ---------------------------------------------------------------------------
# SPARQLQuery fluent builder — advanced features
# ---------------------------------------------------------------------------

class TestSPARQLQueryFluent:
    def test_group_by(self):
        q = (
            select("?type", "(COUNT(?s) AS ?count)")
            .where("?s a ?type")
            .group_by("?type")
            .build()
        )
        assert "GROUP BY ?type" in q

    def test_having(self):
        q = (
            select("?type", "(COUNT(?s) AS ?count)")
            .where("?s a ?type")
            .group_by("?type")
            .having("COUNT(?s) > 10")
            .build()
        )
        assert "HAVING(COUNT(?s) > 10)" in q

    def test_group_by_and_having_together(self):
        q = (
            select("?type", "(COUNT(?s) AS ?count)")
            .where("?s a ?type")
            .group_by("?type")
            .having("COUNT(?s) > 5")
            .build()
        )
        lines = q.splitlines()
        group_idx = next(i for i, l in enumerate(lines) if "GROUP BY" in l)
        having_idx = next(i for i, l in enumerate(lines) if "HAVING" in l)
        assert group_idx < having_idx

    def test_prefix_declaration(self):
        q = (
            select("?s")
            .prefix("ex", "http://example.org/")
            .where("?s a ex:Thing")
            .build()
        )
        assert "PREFIX ex: <http://example.org/>" in q

    def test_multiple_prefix_declarations(self):
        q = (
            select("?s", "?label")
            .prefix("ex", "http://example.org/")
            .prefix("rdfs", "http://www.w3.org/2000/01/rdf-schema#")
            .where("?s a ex:Thing")
            .where("?s rdfs:label ?label")
            .build()
        )
        assert "PREFIX ex: <http://example.org/>" in q
        assert "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>" in q

    def test_prefix_appears_before_select(self):
        q = (
            select("?s")
            .prefix("ex", "http://example.org/")
            .where("?s a ex:Thing")
            .build()
        )
        prefix_pos = q.index("PREFIX")
        select_pos = q.index("SELECT")
        assert prefix_pos < select_pos

    def test_fluent_chaining_returns_same_object(self):
        query = select("?s")
        assert query.where("?s ?p ?o") is query
        assert query.distinct() is query
        assert query.limit(10) is query
        assert query.offset(0) is query
        assert query.order_by("?s") is query
        assert query.group_by("?s") is query
        assert query.having("COUNT(?s) > 1") is query
        assert query.filter("?s > 0") is query
        assert query.prefix("ex", "http://example.org/") is query

    def test_build_returns_string(self):
        q = select("?s").where("?s ?p ?o").build()
        assert isinstance(q, str)

    def test_where_block_structure(self):
        q = select("?s").where("?s ?p ?o").build()
        assert "WHERE {" in q
        assert "}" in q

    def test_offset_zero_included(self):
        q = select("?s").where("?s ?p ?o").offset(0).build()
        assert "OFFSET 0" in q

    def test_order_by_desc(self):
        q = select("?s").where("?s ?p ?o").order_by("DESC(?s)").build()
        assert "ORDER BY DESC(?s)" in q
