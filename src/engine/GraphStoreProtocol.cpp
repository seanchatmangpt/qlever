// Copyright 2024, University of Freiburg
// Chair of Algorithms and Data Structures
// Authors: Julian Mundhahs <mundhahj@tf.uni-freiburg.de>

#ifndef QLEVER_REDUCED_FEATURE_SET_FOR_CPP17
#include "engine/GraphStoreProtocol.h"

#include "engine/DatalogParser.h"
#include "engine/JsonLdParser.h"
#include "engine/RdfXmlParser.h"
#include "engine/ShExParser.h"
#include "parser/Tokenizer.h"
#include "util/http/beast.h"

// ____________________________________________________________________________
void GraphStoreProtocol::throwUnsupportedMediatype(
    const std::string_view& mediatype) {
  throw HttpError(
      boost::beast::http::status::unsupported_media_type,
      absl::StrCat(
          "Mediatype \"", mediatype,
          "\" is not supported for SPARQL Graph Store HTTP Protocol in QLever. "
          "Supported: ",
          toString(ad_utility::MediaType::turtle), ", ",
          toString(ad_utility::MediaType::ntriples), ", ",
          toString(ad_utility::MediaType::n3), ", ",
          toString(ad_utility::MediaType::shacl), ", ",
          toString(ad_utility::MediaType::trig), ", ",
          toString(ad_utility::MediaType::nquads), ", ",
          toString(ad_utility::MediaType::jsonLd), ", ",
          toString(ad_utility::MediaType::rdfXml), ", ",
          toString(ad_utility::MediaType::datalog), ", ",
          toString(ad_utility::MediaType::shex), "."));
}

// ____________________________________________________________________________
void GraphStoreProtocol::throwNotYetImplementedHTTPMethod(
    const std::string_view& method) {
  throw std::runtime_error(absl::StrCat(
      method,
      " in the SPARQL Graph Store HTTP Protocol is not yet implemented "
      "in QLever."));
}

// ____________________________________________________________________________
std::vector<TurtleTriple> GraphStoreProtocol::parseTriples(
    const std::string& body, ad_utility::MediaType contentType) {
  using Re2Parser = RdfStringParser<TurtleParser<Tokenizer>>;
  switch (contentType) {
    case ad_utility::MediaType::turtle:
    case ad_utility::MediaType::n3:
    case ad_utility::MediaType::shacl:
    case ad_utility::MediaType::trig:
    case ad_utility::MediaType::ntriples:
    case ad_utility::MediaType::nquads: {
      // TODO<joka921> We could pass in the actual manager here,
      // then the resulting triples could (possibly) be already much
      // smaller. This will be done in a future version where we pass the state
      // of the underlying index more consistently to all parsing and update
      // functions.
      EncodedIriManager encodedIriManager;
      auto parser = Re2Parser(&encodedIriManager);
      parser.setInputStream(body);
      return parser.parseAndReturnAllTriples();
    }
    case ad_utility::MediaType::rdfXml: {
      return RdfXmlParser::parse(body);
    }
    case ad_utility::MediaType::jsonLd: {
      return JsonLdParser::parse(body);
    }
    case ad_utility::MediaType::shex: {
      return ShExParser::parse(body);
    }
    case ad_utility::MediaType::datalog: {
      return DatalogParser::parse(body);
    }
    default: {
      throwUnsupportedMediatype(toString(contentType));
    }
  }
}

// ____________________________________________________________________________
updateClause::GraphUpdate::Triples GraphStoreProtocol::convertTriples(
    const GraphOrDefault& graph, std::vector<TurtleTriple>&& triples,
    Quads::BlankNodeAdder& blankNodeAdder) {
  SparqlTripleSimpleWithGraph::Graph tripleGraph{std::monostate{}};
  if (std::holds_alternative<GraphRef>(graph)) {
    tripleGraph = std::get<GraphRef>(graph);
  }
  auto transformTc =
      [&blankNodeAdder](TripleComponent&& tc) -> TripleComponent {
    if (tc.isString()) {
      return blankNodeAdder.getBlankNodeIndex(tc.getString());
    } else {
      return std::move(tc);
    }
  };
  auto transformTurtleTriple = [&tripleGraph,
                                &transformTc](TurtleTriple&& triple) {
    AD_CORRECTNESS_CHECK(triple.graphIri_.isId() &&
                         triple.graphIri_.getId() ==
                             qlever::specialIds().at(DEFAULT_GRAPH_IRI));

    return SparqlTripleSimpleWithGraph(
        transformTc(std::move(triple.subject_)),
        transformTc(std::move(triple.predicate_)),
        transformTc(std::move(triple.object_)), tripleGraph);
  };
  return {ad_utility::transform(std::move(triples), transformTurtleTriple),
          blankNodeAdder.localVocab_.clone()};
}

// ____________________________________________________________________________
ParsedQuery GraphStoreProtocol::transformGet(
    const GraphOrDefault& graph, const EncodedIriManager* encodedIriManager) {
  // Construct the parsed query from its short equivalent SPARQL Update
  // string. This is easier and also provides e.g. the `_originalString` field.
  auto getQuery = [&graph]() -> std::string {
    if (const auto* iri =
            std::get_if<ad_utility::triple_component::Iri>(&graph)) {
      return absl::StrCat("CONSTRUCT { ?s ?p ?o } WHERE { GRAPH ",
                          iri->toStringRepresentation(), " { ?s ?p ?o } }");
    } else {
      return "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }";
    }
  };
  return SparqlParser::parseQuery(encodedIriManager, getQuery());
}

// ____________________________________________________________________________
ParsedQuery GraphStoreProtocol::transformDelete(const GraphOrDefault& graph,
                                                const Index& index) {
  // Construct the parsed update from its short equivalent SPARQL Update string.
  // This is easier and also provides e.g. the `_originalString` field.
  auto getUpdate = [&graph]() -> std::string {
    if (const auto* iri =
            std::get_if<ad_utility::triple_component::Iri>(&graph)) {
      return absl::StrCat("DROP GRAPH ", iri->toStringRepresentation());
    } else {
      return "DROP DEFAULT";
    }
  };
  return ad_utility::getSingleElement(SparqlParser::parseUpdate(
      index.getBlankNodeManager(), &index.encodedIriManager(), getUpdate()));
}

#endif
