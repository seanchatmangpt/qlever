// Copyright 2024, University of Freiburg
// Chair of Algorithms and Data Structures

#ifndef QLEVER_SRC_ENGINE_RDFXMLPARSER_H
#define QLEVER_SRC_ENGINE_RDFXMLPARSER_H

#include <regex>
#include <string>
#include <string_view>
#include <vector>

#include "parser/RdfParser.h"

// A simple RDF/XML parser that handles the specific format produced by QLever's
// own RDF/XML export (see `ExportQueryExecutionTrees.cpp`). This is not a
// general-purpose RDF/XML parser.
//
// The expected format is:
//   <rdf:Description rdf:about="SUBJECT">
//     <PREDICATE rdf:resource="OBJECT"/>      (IRI object)
//     <PREDICATE>LITERAL</PREDICATE>          (literal object)
//   </rdf:Description>
class RdfXmlParser {
 public:
  // Parse the given RDF/XML string and return a vector of `TurtleTriple`.
  static std::vector<TurtleTriple> parse(const std::string& input) {
    std::vector<TurtleTriple> result;

    // Guard against excessively large inputs to prevent ReDoS with the
    // backtracking regex engine. 100 MB is generous for Graph Store Protocol.
    constexpr size_t maxInputSize = 100 * 1024 * 1024;
    if (input.size() > maxInputSize) {
      throw std::runtime_error(
          "RDF/XML input exceeds maximum allowed size of 100 MB");
    }

    // Regex to match <rdf:Description rdf:about="..."> blocks.
    // We capture the subject IRI and the inner content of each block.
    static const std::regex descriptionRegex(
        R"(<rdf:Description\s+rdf:about="([^"]*)">([\s\S]*?)</rdf:Description>)");

    // Regex to match predicates with IRI objects:
    //   <prefix:local rdf:resource="OBJECT"/>
    static const std::regex iriObjectRegex(
        R"(<([a-zA-Z_][\w.-]*:[a-zA-Z_][\w.-]*)\s+rdf:resource="([^"]*)"\s*/>)");

    // Regex to match predicates with literal objects:
    //   <prefix:local>LITERAL</prefix:local>
    static const std::regex literalObjectRegex(
        R"(<([a-zA-Z_][\w.-]*:[a-zA-Z_][\w.-]*)\s*>([^<]*)</\1\s*>)");

    auto descBegin =
        std::sregex_iterator(input.begin(), input.end(), descriptionRegex);
    auto descEnd = std::sregex_iterator();

    for (auto it = descBegin; it != descEnd; ++it) {
      const std::smatch& descMatch = *it;
      std::string subjectIri = unescapeXml(descMatch[1].str());
      std::string blockContent = descMatch[2].str();

      // Find IRI object triples within this block.
      auto iriBegin = std::sregex_iterator(blockContent.begin(),
                                           blockContent.end(), iriObjectRegex);
      auto iterEnd = std::sregex_iterator();
      for (auto jt = iriBegin; jt != iterEnd; ++jt) {
        const std::smatch& tripleMatch = *jt;
        std::string predicate = expandPrefixedName(tripleMatch[1].str());
        std::string objectIri = unescapeXml(tripleMatch[2].str());

        TurtleTriple triple;
        triple.subject_ =
            TripleComponent::Iri::fromIriref(wrapInAngleBrackets(subjectIri));
        triple.predicate_ =
            TripleComponent::Iri::fromIriref(wrapInAngleBrackets(predicate));
        triple.object_ =
            TripleComponent::Iri::fromIriref(wrapInAngleBrackets(objectIri));
        result.push_back(std::move(triple));
      }

      // Find literal object triples within this block.
      auto litBegin = std::sregex_iterator(
          blockContent.begin(), blockContent.end(), literalObjectRegex);
      auto litEnd = std::sregex_iterator();
      for (auto jt = litBegin; jt != litEnd; ++jt) {
        const std::smatch& tripleMatch = *jt;
        std::string predicate = expandPrefixedName(tripleMatch[1].str());
        std::string literalValue = unescapeXml(tripleMatch[2].str());

        TurtleTriple triple;
        triple.subject_ =
            TripleComponent::Iri::fromIriref(wrapInAngleBrackets(subjectIri));
        triple.predicate_ =
            TripleComponent::Iri::fromIriref(wrapInAngleBrackets(predicate));
        triple.object_ =
            TripleComponent::Literal::literalWithoutQuotes(literalValue);
        result.push_back(std::move(triple));
      }
    }

    return result;
  }

 private:
  // Wrap a raw IRI string in angle brackets: "http://..." -> "<http://...>"
  static std::string wrapInAngleBrackets(const std::string& iri) {
    return absl::StrCat("<", iri, ">");
  }

  // Expand known XML/RDF namespace prefixes to their full IRI form.
  static std::string expandPrefixedName(const std::string& prefixedName) {
    // The only namespace used in QLever's RDF/XML output.
    static const std::string rdfPrefix =
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#";

    auto colonPos = prefixedName.find(':');
    if (colonPos == std::string::npos) {
      return prefixedName;
    }
    std::string prefix = prefixedName.substr(0, colonPos);
    std::string local = prefixedName.substr(colonPos + 1);

    if (prefix == "rdf") {
      return absl::StrCat(rdfPrefix, local);
    }

    // For unknown prefixes, return as-is (should not happen with QLever's
    // output).
    return prefixedName;
  }

  // Unescape XML entities in a string.
  static std::string unescapeXml(const std::string& input) {
    std::string result;
    result.reserve(input.size());
    for (size_t i = 0; i < input.size(); ++i) {
      if (input[i] == '&') {
        if (input.compare(i, 5, "&amp;") == 0) {
          result += '&';
          i += 4;
        } else if (input.compare(i, 4, "&lt;") == 0) {
          result += '<';
          i += 3;
        } else if (input.compare(i, 4, "&gt;") == 0) {
          result += '>';
          i += 3;
        } else if (input.compare(i, 6, "&apos;") == 0) {
          result += '\'';
          i += 5;
        } else if (input.compare(i, 6, "&quot;") == 0) {
          result += '"';
          i += 5;
        } else {
          result += input[i];
        }
      } else {
        result += input[i];
      }
    }
    return result;
  }
};

#endif  // QLEVER_SRC_ENGINE_RDFXMLPARSER_H
