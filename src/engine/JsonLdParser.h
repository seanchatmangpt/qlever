// Copyright 2024, University of Freiburg
// Chair of Algorithms and Data Structures

#ifndef QLEVER_SRC_ENGINE_JSONLDPARSER_H
#define QLEVER_SRC_ENGINE_JSONLDPARSER_H

#include <string>
#include <vector>

#include "parser/NormalizedString.h"
#include "parser/RdfParser.h"
#include "util/json.h"

// A simple JSON-LD parser that handles the specific format produced by QLever's
// own JSON-LD export (see `ExportQueryExecutionTrees.cpp`). This parser is NOT
// a general-purpose JSON-LD parser; it only supports the subset of JSON-LD that
// QLever produces.
//
// The expected format is:
//   {
//     "@graph": [
//       {"@id": "http://example.org/s", "http://example.org/p":
//           {"@id": "http://example.org/o"}},
//       {"@id": "http://example.org/s", "http://example.org/p": "literal"}
//     ]
//   }
class JsonLdParser {
 public:
  // Parse the given JSON-LD string and return a vector of TurtleTriples.
  static std::vector<TurtleTriple> parse(const std::string& input) {
    std::vector<TurtleTriple> result;

    nlohmann::json doc = nlohmann::json::parse(input);

    // Collect the node objects: either from "@graph" array or treat the
    // document itself as a single node.
    std::vector<std::reference_wrapper<const nlohmann::json>> nodes;
    if (doc.contains("@graph") && doc["@graph"].is_array()) {
      for (const auto& node : doc["@graph"]) {
        nodes.emplace_back(node);
      }
    } else if (doc.is_object()) {
      nodes.emplace_back(doc);
    }

    for (const auto& nodeRef : nodes) {
      const auto& node = nodeRef.get();
      if (!node.is_object() || !node.contains("@id")) {
        continue;
      }

      std::string subjectIri = node["@id"].get<std::string>();
      TripleComponent subject =
          TripleComponent::Iri::fromIrirefWithoutBrackets(subjectIri);

      for (const auto& [key, value] : node.items()) {
        if (key == "@id") {
          continue;
        }

        TripleComponent predicate =
            TripleComponent::Iri::fromIrirefWithoutBrackets(key);

        TripleComponent object = parseValue(value);

        TurtleTriple triple;
        triple.subject_ = subject;
        triple.predicate_ = predicate;
        triple.object_ = object;
        result.push_back(std::move(triple));
      }
    }

    return result;
  }

 private:
  // Parse a JSON-LD value into a TripleComponent.
  static TripleComponent parseValue(const nlohmann::json& value) {
    // Object with @id means an IRI reference.
    if (value.is_object() && value.contains("@id")) {
      return TripleComponent::Iri::fromIrirefWithoutBrackets(
          value["@id"].get<std::string>());
    }

    // String value: could be a plain literal or a quoted RDF literal with
    // language tag or datatype (as produced by QLever's export via
    // validRDFLiteralFromNormalized).
    if (value.is_string()) {
      std::string str = value.get<std::string>();
      // If the string starts with a quote, it is an RDF literal in normalized
      // form (e.g., "\"Alice\"" or "\"Alice\"@en" or
      // "\"42\"^^<xsd:integer>").
      if (!str.empty() && str.front() == '"') {
        return TripleComponent::Literal::fromEscapedRdfLiteral(str);
      }
      // Otherwise treat as a plain string literal.
      return TripleComponent::Literal::literalWithNormalizedContent(
          asNormalizedStringViewUnsafe(str));
    }

    // Fallback for other JSON types: convert to string and wrap as literal.
    std::string str = value.dump();
    return TripleComponent::Literal::literalWithNormalizedContent(
        asNormalizedStringViewUnsafe(str));
  }
};

#endif  // QLEVER_SRC_ENGINE_JSONLDPARSER_H
