// Copyright 2024, University of Freiburg
// Chair of Algorithms and Data Structures

#ifndef QLEVER_SRC_ENGINE_SHEXPARSER_H
#define QLEVER_SRC_ENGINE_SHEXPARSER_H

#include <string>
#include <string_view>
#include <vector>

#include "parser/RdfParser.h"

// A simple parser for the ShEx (Shape Expressions) compact syntax as produced
// by QLever's own ShEx export. Each shape block represents one triple:
//
//   <subject> {
//     <predicate> [<object>] ;
//   }
//
// The parser skips PREFIX declarations and extracts triples from shape blocks.
class ShExParser {
 public:
  // Parse the given ShEx string and return all triples.
  static std::vector<TurtleTriple> parse(const std::string& input) {
    std::vector<TurtleTriple> result;
    std::string_view sv = input;

    // Skip leading whitespace and PREFIX declarations.
    skipPrefixes(sv);

    // Parse shape blocks until input is exhausted.
    while (!sv.empty()) {
      skipWhitespace(sv);
      if (sv.empty()) {
        break;
      }

      // Extract the subject IRI (everything up to '{').
      auto openBrace = sv.find('{');
      if (openBrace == std::string_view::npos) {
        // No '{' found anywhere: no more well-formed blocks remain.
        // Skip to end rather than silently dropping all remaining input.
        sv = {};
        continue;
      }
      std::string_view subjectStr = trim(sv.substr(0, openBrace));
      sv.remove_prefix(openBrace + 1);

      // Extract the predicate IRI (everything up to '[').
      auto openBracket = sv.find('[');
      if (openBracket == std::string_view::npos) {
        // Malformed block (no '['): skip to closing '}' of this block rather
        // than aborting all remaining input. These parsers only round-trip
        // QLever's own output, so partial failures should not drop everything.
        auto closeBrace = sv.find('}');
        sv = (closeBrace == std::string_view::npos) ? std::string_view{} : sv.substr(closeBrace + 1);
        continue;
      }
      std::string_view predicateStr = trim(sv.substr(0, openBracket));
      sv.remove_prefix(openBracket + 1);

      // Extract the object (everything up to ']'). The object may contain
      // nested angle brackets (for datatype IRIs in literals like
      // "value"^^<iri>), so we cannot simply search for ']'.
      auto closeBracket = findClosingBracket(sv);
      if (closeBracket == std::string_view::npos) {
        // Malformed block (no ']'): skip to closing '}' of this block.
        auto closeBrace = sv.find('}');
        sv = (closeBrace == std::string_view::npos) ? std::string_view{} : sv.substr(closeBrace + 1);
        continue;
      }
      std::string_view objectStr = trim(sv.substr(0, closeBracket));
      sv.remove_prefix(closeBracket + 1);

      // Skip past the closing ';' and '}'.
      auto closeBrace = sv.find('}');
      if (closeBrace != std::string_view::npos) {
        sv.remove_prefix(closeBrace + 1);
      }

      // Build the TurtleTriple from the extracted strings.
      result.push_back(makeTriple(subjectStr, predicateStr, objectStr));
    }

    return result;
  }

 private:
  // Skip all PREFIX declarations at the beginning of the input.
  static void skipPrefixes(std::string_view& sv) {
    while (true) {
      skipWhitespace(sv);
      if (sv.substr(0, 6) == "PREFIX" || sv.substr(0, 6) == "prefix") {
        // Skip to end of line.
        auto newline = sv.find('\n');
        if (newline == std::string_view::npos) {
          sv = {};
          return;
        }
        sv.remove_prefix(newline + 1);
      } else {
        break;
      }
    }
  }

  // Skip leading whitespace characters.
  static void skipWhitespace(std::string_view& sv) {
    auto pos = sv.find_first_not_of(" \t\n\r");
    if (pos == std::string_view::npos) {
      sv = {};
    } else {
      sv.remove_prefix(pos);
    }
  }

  // Trim whitespace from both ends of a string_view.
  static std::string_view trim(std::string_view sv) {
    auto start = sv.find_first_not_of(" \t\n\r");
    if (start == std::string_view::npos) {
      return {};
    }
    auto end = sv.find_last_not_of(" \t\n\r");
    return sv.substr(start, end - start + 1);
  }

  // Find the position of the closing ']' that matches the opening bracket.
  // The object content may contain angle-bracketed IRIs, so we need to skip
  // over those.
  static size_t findClosingBracket(std::string_view sv) {
    bool inAngleBrackets = false;
    bool inQuotes = false;
    for (size_t i = 0; i < sv.size(); ++i) {
      char c = sv[i];
      if (inQuotes) {
        if (c == '\\' && i + 1 < sv.size()) {
          // Skip escaped character.
          ++i;
          continue;
        }
        if (c == '"') {
          inQuotes = false;
        }
        continue;
      }
      if (inAngleBrackets) {
        if (c == '>') {
          inAngleBrackets = false;
        }
        continue;
      }
      if (c == '"') {
        inQuotes = true;
      } else if (c == '<') {
        inAngleBrackets = true;
      } else if (c == ']') {
        return i;
      }
    }
    return std::string_view::npos;
  }

  // Construct a TripleComponent from a string that is either an IRI
  // (surrounded by angle brackets) or a literal.
  static TripleComponent makeComponent(std::string_view str) {
    using Iri = ad_utility::triple_component::Iri;
    using Literal = ad_utility::triple_component::Literal;

    if (str.empty()) {
      return TripleComponent{std::string(str)};
    }

    if (str.front() == '<' && str.back() == '>') {
      // IRI in angle brackets.
      return TripleComponent{Iri::fromIriref(str)};
    }

    if (str.front() == '"') {
      // Literal, possibly with datatype or language tag.
      return TripleComponent{Literal::fromEscapedRdfLiteral(str)};
    }

    // Fallback: return as string.
    return TripleComponent{std::string(str)};
  }

  // Construct a TurtleTriple from the subject, predicate, and object strings.
  static TurtleTriple makeTriple(std::string_view subject,
                                 std::string_view predicate,
                                 std::string_view object) {
    TurtleTriple triple;
    triple.subject_ = makeComponent(subject);
    triple.predicate_ = makeComponent(predicate);
    triple.object_ = makeComponent(object);
    // graphIri_ is initialized to the default graph by TurtleTriple's default.
    return triple;
  }
};

#endif  // QLEVER_SRC_ENGINE_SHEXPARSER_H
