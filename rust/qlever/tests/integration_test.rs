// Integration tests for the `qlever` safe Rust wrapper.
//
// These tests exercise the full build-index → query → update → query cycle.
// They require a real QLever C library to be linked.
//
// Running these tests requires:
//   1. A pre-built libqlever_c.a in the directory pointed to by QLEVER_LIB_DIR.
//   2. Test data (a Turtle file) accessible at the path used in each test.
//
// When QLEVER_LIB_DIR is not set the tests are skipped via the
// `skip_without_lib` helper so that `cargo test` on a machine without a
// QLever build still passes.

use std::path::PathBuf;

// ---------------------------------------------------------------------------
// Helper: skip test if QLEVER_LIB_DIR is not set (library not built yet).
// ---------------------------------------------------------------------------
fn lib_available() -> bool {
    std::env::var("QLEVER_LIB_DIR").is_ok()
}

// ---------------------------------------------------------------------------
// Helper: create a minimal Turtle file with a handful of triples.
// ---------------------------------------------------------------------------
fn write_test_turtle(dir: &std::path::Path) -> PathBuf {
    let path = dir.join("test.ttl");
    std::fs::write(
        &path,
        r#"@prefix ex: <http://example.org/> .
ex:Alice  ex:knows   ex:Bob   .
ex:Bob    ex:knows   ex:Carol .
ex:Carol  ex:knows   ex:Alice .
ex:Alice  ex:age     "30"^^<http://www.w3.org/2001/XMLSchema#integer> .
ex:Bob    ex:age     "25"^^<http://www.w3.org/2001/XMLSchema#integer> .
"#,
    )
    .expect("failed to write test Turtle file");
    path
}

// ---------------------------------------------------------------------------
// Test: qlever::Qlever::version() returns a non-empty string.
// ---------------------------------------------------------------------------
#[test]
fn version_is_non_empty() {
    let v = qlever::Qlever::version();
    assert!(!v.is_empty(), "version should not be empty");
}

// ---------------------------------------------------------------------------
// Test: full build → load → query → update → query cycle.
// ---------------------------------------------------------------------------
#[test]
fn build_query_update_cycle() {
    if !lib_available() {
        eprintln!("Skipping integration test: QLEVER_LIB_DIR not set");
        return;
    }

    let tmp = tempfile::tempdir().expect("failed to create temp dir");
    let base = tmp.path().join("idx").to_string_lossy().into_owned();
    let ttl = write_test_turtle(tmp.path());

    // ---- Build index -------------------------------------------------------
    qlever::IndexBuilderOptions::new(base.as_str(), ttl.to_str().unwrap())
        .memory_limit_gb(1.0)
        .build()
        .expect("index build should succeed");

    // ---- Open engine -------------------------------------------------------
    let engine = qlever::EngineOptions::new(base.as_str())
        .memory_limit_gb(1.0)
        .persist_updates(false)
        .open()
        .expect("engine open should succeed");

    // ---- COUNT query -------------------------------------------------------
    let result = engine
        .query("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }")
        .expect("COUNT query should succeed");

    let json: serde_json::Value =
        serde_json::from_str(&result).expect("result should be valid JSON");
    let count_str = json["results"]["bindings"][0]["c"]["value"]
        .as_str()
        .expect("expected a count binding");
    let count: u64 = count_str.parse().expect("count should be a number");
    assert_eq!(count, 5, "expected 5 triples in test dataset");

    // ---- SPARQL Update: insert a new triple --------------------------------
    let meta = engine
        .update(
            "INSERT DATA { \
             <http://example.org/Dave> \
             <http://example.org/knows> \
             <http://example.org/Alice> }",
        )
        .expect("INSERT DATA should succeed");

    let meta_json: serde_json::Value =
        serde_json::from_str(&meta).expect("update metadata should be valid JSON");
    // The metadata is an array with one entry per parsed update operation.
    assert!(meta_json.is_array(), "update metadata should be a JSON array");

    // ---- COUNT query after update ------------------------------------------
    let result2 = engine
        .query("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }")
        .expect("second COUNT query should succeed");
    let json2: serde_json::Value = serde_json::from_str(&result2).unwrap();
    let count2: u64 = json2["results"]["bindings"][0]["c"]["value"]
        .as_str()
        .unwrap()
        .parse()
        .unwrap();
    assert_eq!(count2, 6, "expected 6 triples after INSERT DATA");
}

// ---------------------------------------------------------------------------
// Test: a query with a NUL byte in the string returns an error.
// ---------------------------------------------------------------------------
#[test]
fn query_with_nul_byte_returns_error() {
    if !lib_available() {
        eprintln!("Skipping: QLEVER_LIB_DIR not set");
        return;
    }

    let tmp = tempfile::tempdir().unwrap();
    let base = tmp.path().join("idx2").to_string_lossy().into_owned();
    let ttl = write_test_turtle(tmp.path());

    qlever::IndexBuilderOptions::new(base.as_str(), ttl.to_str().unwrap())
        .build()
        .unwrap();

    let engine = qlever::EngineOptions::new(base.as_str()).open().unwrap();

    // A query string with an interior NUL byte must return NulByte error.
    let bad_query = "SELECT * WHERE { ?s ?p ?o }\0 EXTRA";
    let err = engine.query(bad_query).unwrap_err();
    assert!(
        matches!(err, qlever::Error::NulByte),
        "expected NulByte error, got: {err}"
    );
}
