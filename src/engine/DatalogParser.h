// Copyright 2024, University of Freiburg
// Chair of Algorithms and Data Structures

#ifndef QLEVER_SRC_ENGINE_DATALOGPARSER_H
#define QLEVER_SRC_ENGINE_DATALOGPARSER_H

#include <string>
#include <string_view>
#include <vector>

#include "parser/LiteralOrIri.h"
#include "parser/RdfParser.h"

// A simple Datalog parser that handles the specific format produced by QLever's
// own Datalog export. Format: predicate(subject, object).
//
// Examples:
//   <http://example.org/knows>(<http://example.org/Alice>,
//   <http://example.org/Bob>).
//   <http://example.org/name>(<http://example.org/Alice>,
//   "Alice"^^<http://www.w3.org/2001/XMLSchema#string>).
class DatalogParser {
 public:
  static std::vector<TurtleTriple> parse(const std::string& input) {
    std::vector<TurtleTriple> result;

    std::string_view remaining(input);
    while (!remaining.empty()) {
      // Skip whitespace and newlines.
      auto pos = remaining.find_first_not_of(" \t\r\n");
      if (pos == std::string_view::npos) break;
      remaining = remaining.substr(pos);
      if (remaining.empty()) break;

      // Find the opening parenthesis — everything before it is the predicate.
      auto parenOpen = findUnquoted(remaining, '(');
      if (parenOpen == std::string_view::npos) {
        // Malformed line (no '('): skip to next line rather than aborting all
        // remaining input. These parsers only round-trip QLever's own output,
        // so partial failures should not silently drop everything that follows.
        auto nl = remaining.find('\n');
        remaining = (nl == std::string_view::npos) ? std::string_view{}
                                                   : remaining.substr(nl + 1);
        continue;
      }

      std::string predicate(remaining.substr(0, parenOpen));
      trimInPlace(predicate);
      remaining = remaining.substr(parenOpen + 1);

      // Find the comma separating subject and object.
      auto comma = findUnquoted(remaining, ',');
      if (comma == std::string_view::npos) {
        // Malformed statement (no ','): skip to next line.
        auto nl = remaining.find('\n');
        remaining = (nl == std::string_view::npos) ? std::string_view{}
                                                   : remaining.substr(nl + 1);
        continue;
      }

      std::string subject(remaining.substr(0, comma));
      trimInPlace(subject);
      remaining = remaining.substr(comma + 1);

      // Find the closing ")." — the object is everything before it.
      auto parenClose = findUnquoted(remaining, ')');
      if (parenClose == std::string_view::npos) {
        // Malformed statement (no ')'): skip to next line.
        auto nl = remaining.find('\n');
        remaining = (nl == std::string_view::npos) ? std::string_view{}
                                                   : remaining.substr(nl + 1);
        continue;
      }

      std::string object(remaining.substr(0, parenClose));
      trimInPlace(object);
      remaining = remaining.substr(parenClose + 1);

      // Skip the trailing dot and whitespace.
      pos = remaining.find_first_not_of(" \t.");
      if (pos != std::string_view::npos) {
        remaining = remaining.substr(pos);
      } else {
        remaining = {};
      }

      // Build the TurtleTriple. The graphIri_ field is initialized to
      // DEFAULT_GRAPH_IRI by the TurtleTriple default constructor.
      TurtleTriple triple;
      triple.subject_ = toTripleComponent(subject);
      triple.predicate_ = toTripleComponent(predicate);
      triple.object_ = toTripleComponent(object);
      result.push_back(std::move(triple));
    }

    return result;
  }

 private:
  using Iri = ad_utility::triple_component::Iri;
  using LiteralOrIri = ad_utility::triple_component::LiteralOrIri;

  // Find a character in the string view, skipping quoted sections.
  static size_t findUnquoted(std::string_view sv, char target) {
    bool inQuote = false;
    bool escaped = false;
    for (size_t i = 0; i < sv.size(); ++i) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (sv[i] == '\\') {
        escaped = true;
        continue;
      }
      if (sv[i] == '"') {
        inQuote = !inQuote;
        continue;
      }
      if (!inQuote && sv[i] == target) {
        return i;
      }
    }
    return std::string_view::npos;
  }

  static void trimInPlace(std::string& s) {
    auto start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) {
      s.clear();
      return;
    }
    auto end = s.find_last_not_of(" \t\r\n");
    s = s.substr(start, end - start + 1);
  }

  // Convert a string to a TripleComponent. IRIs are angle-bracketed (<...>),
  // literals start with a double quote (").
  static TripleComponent toTripleComponent(const std::string& s) {
    if (s.size() >= 2 && s.front() == '<' && s.back() == '>') {
      // IRI in angle brackets.
      return TripleComponent(Iri::fromIriref(s));
    }
    if (s.size() >= 2 && s.front() == '"') {
      // RDF literal, possibly with language tag or datatype.
      return parseLiteral(s);
    }
    // Fallback: treat as IRI without brackets.
    return TripleComponent(Iri::fromIrirefWithoutBrackets(s));
  }

  // Parse an RDF literal in the form "content", "content"@lang, or
  // "content"^^<datatype>. The content may contain escaped characters.
  static TripleComponent parseLiteral(const std::string& s) {
    // Find the closing quote of the literal content, handling escapes.
    size_t closeQuote = findClosingQuote(s);
    if (closeQuote == std::string::npos || closeQuote == 0) {
      throw std::runtime_error("Datalog parse error: malformed literal: " + s);
    }

    std::string_view quotedPart(s.data(), closeQuote + 1);
    std::string_view suffix(s.data() + closeQuote + 1,
                            s.size() - closeQuote - 1);

    if (suffix.empty()) {
      // Plain literal: "content"
      return TripleComponent(
          Literal::fromEscapedRdfLiteral(quotedPart.data(), quotedPart.size()));
    } else if (suffix.size() >= 2 && suffix[0] == '@') {
      // Language-tagged literal: "content"@lang
      // Reconstruct the full literal string with language tag for parsing
      std::string fullLiteral(quotedPart.begin(), quotedPart.end());
      fullLiteral.append(suffix.begin(), suffix.end());
      return TripleComponent(Literal::fromEscapedRdfLiteral(fullLiteral));
    } else if (suffix.size() >= 3 && suffix[0] == '^' && suffix[1] == '^') {
      // Datatyped literal: "content"^^<datatype>
      // Reconstruct the full literal string with datatype for parsing
      std::string fullLiteral(quotedPart.begin(), quotedPart.end());
      fullLiteral.append(suffix.begin(), suffix.end());
      return TripleComponent(Literal::fromEscapedRdfLiteral(fullLiteral));
    } else {
      throw std::runtime_error(
          "Datalog parse error: unexpected literal suffix in: " + s);
    }
  }

  // Find the position of the closing '"' in a quoted literal string,
  // properly handling backslash escapes.
  static size_t findClosingQuote(const std::string& s) {
    // s[0] should be the opening '"'.
    bool escaped = false;
    for (size_t i = 1; i < s.size(); ++i) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (s[i] == '\\') {
        escaped = true;
        continue;
      }
      if (s[i] == '"') {
        return i;
      }
    }
    return std::string::npos;
  }
};

#endif  // QLEVER_SRC_ENGINE_DATALOGPARSER_H
