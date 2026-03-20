"""Tests for utils.rdf_utils: iri, literal, escape_sparql_string, PrefixMap, parse_ntriples*."""
from __future__ import annotations

import pytest

from utils.rdf_utils import (
    PrefixMap,
    escape_sparql_string,
    iri,
    literal,
    parse_ntriples,
    parse_ntriples_line,
)


# ---------------------------------------------------------------------------
# iri()
# ---------------------------------------------------------------------------

class TestIri:
    def test_wraps_plain_url(self):
        assert iri("http://example.org/foo") == "<http://example.org/foo>"

    def test_idempotent_already_wrapped(self):
        wrapped = "<http://example.org/foo>"
        assert iri(wrapped) == wrapped

    def test_wraps_empty_string(self):
        assert iri("") == "<>"

    def test_wraps_urn(self):
        assert iri("urn:isbn:0451450523") == "<urn:isbn:0451450523>"

    def test_idempotent_only_if_both_brackets_present(self):
        # A string starting with < but not ending with > is not yet wrapped
        assert iri("<http://example.org/foo") == "<<http://example.org/foo>"


# ---------------------------------------------------------------------------
# escape_sparql_string()
# ---------------------------------------------------------------------------

class TestEscapeSparqlString:
    def test_plain_string_unchanged(self):
        assert escape_sparql_string("hello world") == "hello world"

    def test_escapes_double_quote(self):
        assert escape_sparql_string('say "hi"') == 'say \\"hi\\"'

    def test_escapes_newline(self):
        assert escape_sparql_string("line1\nline2") == "line1\\nline2"

    def test_escapes_carriage_return(self):
        assert escape_sparql_string("a\rb") == "a\\rb"

    def test_escapes_tab(self):
        assert escape_sparql_string("a\tb") == "a\\tb"

    def test_escapes_backslash(self):
        assert escape_sparql_string("back\\slash") == "back\\\\slash"

    def test_backslash_before_quote(self):
        # backslash then quote: both must be escaped
        assert escape_sparql_string('\\"') == '\\\\\\"'

    def test_empty_string(self):
        assert escape_sparql_string("") == ""

    def test_multiple_special_chars(self):
        result = escape_sparql_string('a\n"b\\c')
        assert result == 'a\\n\\"b\\\\c'


# ---------------------------------------------------------------------------
# literal()
# ---------------------------------------------------------------------------

class TestLiteral:
    def test_plain_literal(self):
        assert literal("hello") == '"hello"'

    def test_lang_tagged_literal(self):
        assert literal("hello", lang="en") == '"hello"@en'

    def test_datatyped_literal_plain_iri(self):
        result = literal("42", datatype="http://www.w3.org/2001/XMLSchema#integer")
        assert result == '"42"^^<http://www.w3.org/2001/XMLSchema#integer>'

    def test_datatyped_literal_already_bracketed(self):
        result = literal("42", datatype="<http://www.w3.org/2001/XMLSchema#integer>")
        assert result == '"42"^^<http://www.w3.org/2001/XMLSchema#integer>'

    def test_lang_and_datatype_raises(self):
        with pytest.raises(ValueError):
            literal("bad", lang="en", datatype="http://example.org/dt")

    def test_special_chars_escaped_in_literal(self):
        result = literal('say "hi"')
        assert result == '"say \\"hi\\""'

    def test_empty_string_literal(self):
        assert literal("") == '""'

    def test_lang_tag_preserved(self):
        result = literal("Bonjour", lang="fr")
        assert result.endswith("@fr")


# ---------------------------------------------------------------------------
# PrefixMap
# ---------------------------------------------------------------------------

class TestPrefixMap:
    def test_default_includes_common_prefixes(self):
        pm = PrefixMap()
        assert "rdf" in pm
        assert "rdfs" in pm
        assert "xsd" in pm
        assert "owl" in pm
        assert "schema" in pm
        assert "wd" in pm
        assert "wdt" in pm

    def test_include_common_false_empty(self):
        pm = PrefixMap(include_common=False)
        assert len(pm) == 0

    def test_add_prefix(self):
        pm = PrefixMap(include_common=False)
        pm.add("ex", "http://example.org/")
        assert "ex" in pm

    def test_contains_false_for_unknown(self):
        pm = PrefixMap(include_common=False)
        assert "ex" not in pm

    def test_expand_known_prefix(self):
        pm = PrefixMap(include_common=False)
        pm.add("ex", "http://example.org/")
        assert pm.expand("ex:foo") == "<http://example.org/foo>"

    def test_expand_unknown_prefix_returns_as_is(self):
        pm = PrefixMap(include_common=False)
        assert pm.expand("ex:foo") == "ex:foo"

    def test_expand_already_bracketed_returns_as_is(self):
        pm = PrefixMap()
        full = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"
        assert pm.expand(full) == full

    def test_expand_no_colon_returns_as_is(self):
        pm = PrefixMap()
        assert pm.expand("nocolon") == "nocolon"

    def test_shorten_known_iri(self):
        pm = PrefixMap(include_common=False)
        pm.add("ex", "http://example.org/")
        assert pm.shorten("<http://example.org/foo>") == "ex:foo"

    def test_shorten_bare_iri_string(self):
        pm = PrefixMap(include_common=False)
        pm.add("ex", "http://example.org/")
        assert pm.shorten("http://example.org/bar") == "ex:bar"

    def test_shorten_unknown_iri_returns_as_is(self):
        pm = PrefixMap(include_common=False)
        result = pm.shorten("<http://unknown.org/foo>")
        assert result == "<http://unknown.org/foo>"

    def test_to_sparql_prefixes_sorted(self):
        pm = PrefixMap(include_common=False)
        pm.add("zzz", "http://zzz.org/")
        pm.add("aaa", "http://aaa.org/")
        output = pm.to_sparql_prefixes()
        lines = output.splitlines()
        assert lines[0].startswith("PREFIX aaa:")
        assert lines[1].startswith("PREFIX zzz:")

    def test_to_sparql_prefixes_format(self):
        pm = PrefixMap(include_common=False)
        pm.add("ex", "http://example.org/")
        output = pm.to_sparql_prefixes()
        assert output == "PREFIX ex: <http://example.org/>"

    def test_kwargs_prefixes_in_constructor(self):
        pm = PrefixMap(include_common=False, ex="http://example.org/")
        assert "ex" in pm
        assert pm.expand("ex:Thing") == "<http://example.org/Thing>"

    def test_len_after_adds(self):
        pm = PrefixMap(include_common=False)
        assert len(pm) == 0
        pm.add("a", "http://a.org/")
        pm.add("b", "http://b.org/")
        assert len(pm) == 2


# ---------------------------------------------------------------------------
# parse_ntriples_line()
# ---------------------------------------------------------------------------

class TestParseNtriplesLine:
    def test_simple_iri_triple(self):
        line = "<http://a.org/s> <http://a.org/p> <http://a.org/o> ."
        result = parse_ntriples_line(line)
        assert result == (
            "<http://a.org/s>",
            "<http://a.org/p>",
            "<http://a.org/o>",
        )

    def test_literal_object_plain(self):
        line = '<http://a.org/s> <http://a.org/p> "hello" .'
        result = parse_ntriples_line(line)
        assert result is not None
        s, p, o = result
        assert o == '"hello"'

    def test_literal_object_lang_tagged(self):
        line = '<http://a.org/s> <http://a.org/p> "hello"@en .'
        result = parse_ntriples_line(line)
        assert result is not None
        assert result[2] == '"hello"@en'

    def test_literal_object_datatyped(self):
        line = '<http://a.org/s> <http://a.org/p> "42"^^<http://www.w3.org/2001/XMLSchema#integer> .'
        result = parse_ntriples_line(line)
        assert result is not None
        assert result[2] == '"42"^^<http://www.w3.org/2001/XMLSchema#integer>'

    def test_blank_node_subject(self):
        line = '_:b0 <http://a.org/p> <http://a.org/o> .'
        result = parse_ntriples_line(line)
        assert result is not None
        assert result[0] == '_:b0'

    def test_blank_line_returns_none(self):
        assert parse_ntriples_line("") is None
        assert parse_ntriples_line("   ") is None

    def test_comment_line_returns_none(self):
        assert parse_ntriples_line("# this is a comment") is None

    def test_invalid_line_returns_none(self):
        assert parse_ntriples_line("not valid ntriples") is None

    def test_leading_whitespace_allowed(self):
        line = "  <http://a.org/s> <http://a.org/p> <http://a.org/o> ."
        result = parse_ntriples_line(line)
        assert result is not None

    def test_blank_node_object(self):
        line = "<http://a.org/s> <http://a.org/p> _:b1 ."
        result = parse_ntriples_line(line)
        assert result is not None
        assert result[2] == "_:b1"


# ---------------------------------------------------------------------------
# parse_ntriples()
# ---------------------------------------------------------------------------

class TestParseNtriples:
    def test_single_triple(self):
        text = "<http://a.org/s> <http://a.org/p> <http://a.org/o> ."
        result = parse_ntriples(text)
        assert len(result) == 1
        assert result[0] == (
            "<http://a.org/s>",
            "<http://a.org/p>",
            "<http://a.org/o>",
        )

    def test_multiple_triples(self):
        text = (
            "<http://a.org/s> <http://a.org/p1> <http://a.org/o1> .\n"
            "<http://a.org/s> <http://a.org/p2> <http://a.org/o2> .\n"
        )
        result = parse_ntriples(text)
        assert len(result) == 2

    def test_comments_are_skipped(self):
        text = (
            "# comment line\n"
            "<http://a.org/s> <http://a.org/p> <http://a.org/o> .\n"
            "# another comment\n"
        )
        result = parse_ntriples(text)
        assert len(result) == 1

    def test_blank_lines_are_skipped(self):
        text = (
            "\n"
            "<http://a.org/s> <http://a.org/p> <http://a.org/o> .\n"
            "\n"
        )
        result = parse_ntriples(text)
        assert len(result) == 1

    def test_empty_text_returns_empty_list(self):
        assert parse_ntriples("") == []

    def test_mixed_content(self):
        text = (
            "# header\n"
            "<http://a.org/s> <http://a.org/p> \"hello\"@en .\n"
            "\n"
            "<http://a.org/s> <http://a.org/q> <http://a.org/o> .\n"
            "# footer\n"
        )
        result = parse_ntriples(text)
        assert len(result) == 2
        assert result[0][2] == '"hello"@en'
