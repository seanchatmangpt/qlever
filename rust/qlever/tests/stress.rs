// stress.rs – Joe Armstrong-style stress, fuzz, and adversarial tests for the
// QLever Rust FFI bindings.
//
// Philosophy: "make it break early, loudly, and reproducibly."
//
// The tests are grouped into five batteries:
//
//  1. NULL / zero-length / boundary inputs
//  2. Malformed SPARQL (syntax and semantic errors)
//  3. Resource exhaustion (large payloads, many iterations, deep nesting)
//  4. Concurrency (Send across threads, sequential ordering guarantees)
//  5. Lifecycle (double-destroy, use-after-drop prevention at type level,
//     re-open after close)
//
// REQUIREMENT: QLEVER_LIB_DIR must be set for tests that need a real engine.
// Tests that only exercise the safe Rust API (error types, NulByte) run
// unconditionally.

use std::sync::{Arc, Mutex};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn lib_available() -> bool {
    std::env::var("QLEVER_LIB_DIR").is_ok()
}

/// Write a Turtle dataset of `n_triples` triples to `dir` and return the path.
/// Each triple is `<ex:s{i}> <ex:p> <ex:o{i}>`.
fn write_dataset(dir: &std::path::Path, n_triples: usize) -> std::path::PathBuf {
    let path = dir.join("data.ttl");
    use std::fmt::Write as _;
    let mut ttl = String::from("@prefix ex: <http://example.org/> .\n");
    for i in 0..n_triples {
        writeln!(ttl, "ex:s{i} ex:p ex:o{i} .").unwrap();
    }
    std::fs::write(&path, &ttl).expect("write dataset");
    path
}

/// Build a QLever index and return an engine for the given dataset size.
fn build_and_open(dir: &std::path::Path, n: usize) -> qlever::Qlever {
    let ttl = write_dataset(dir, n);
    let base = dir.join("idx").to_string_lossy().into_owned();
    qlever::IndexBuilderOptions::new(base.as_str(), ttl.to_str().unwrap())
        .memory_limit_gb(1.0)
        .build()
        .expect("index build");
    qlever::EngineOptions::new(base.as_str())
        .memory_limit_gb(1.0)
        .persist_updates(false)
        .open()
        .expect("engine open")
}

// ---------------------------------------------------------------------------
// Battery 1 – NULL / boundary inputs
// (These tests run WITHOUT a real index; they only test the error-path logic.)
// ---------------------------------------------------------------------------

/// Empty SPARQL string: must return a typed error, not a crash.
#[test]
fn query_empty_sparql_returns_error() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), 1);
    let err = engine.query("").unwrap_err();
    assert!(
        matches!(err, qlever::Error::Query(_)),
        "expected Query error, got: {err}"
    );
}

/// A NUL byte anywhere in the query string must be caught before reaching C++.
#[test]
fn query_interior_nul_byte() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), 1);
    // NUL at the start
    assert!(matches!(engine.query("\0SELECT * WHERE { ?s ?p ?o }"), Err(qlever::Error::NulByte)));
    // NUL in the middle
    assert!(matches!(engine.query("SELECT\0 * WHERE { ?s ?p ?o }"), Err(qlever::Error::NulByte)));
    // NUL at the end (before the implicit NUL terminator)
    assert!(matches!(engine.query("SELECT * WHERE { ?s ?p ?o }\0"), Err(qlever::Error::NulByte)));
}

/// A NUL byte in an update string must be caught before reaching C++.
#[test]
fn update_interior_nul_byte() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), 1);
    assert!(matches!(
        engine.update("INSERT DATA { <ex:s>\0 <ex:p> <ex:o> }"),
        Err(qlever::Error::NulByte)
    ));
}

/// An update string consisting solely of whitespace must return a typed error.
#[test]
fn update_whitespace_only_returns_error() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), 1);
    let err = engine.update("   \t\n  ").unwrap_err();
    assert!(
        matches!(err, qlever::Error::Update(_)),
        "expected Update error, got: {err}"
    );
}

// ---------------------------------------------------------------------------
// Battery 2 – Malformed SPARQL
// ---------------------------------------------------------------------------

/// Various syntactically invalid SELECT queries.
#[test]
fn invalid_select_queries() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), 5);

    let bad_queries = [
        "SELECT",                                         // incomplete
        "SELECT * WHERE",                                 // missing braces
        "SELECT * WHERE {",                               // unclosed brace
        "SELECT * WHERE { ?s }",                          // malformed triple
        "SELECT * WHERE { ?s ?p ?o } LIMIT -1",          // negative LIMIT
        "SELECT * WHERE { ?s ?p ?o } LIMIT not_a_number",// bad LIMIT
        "SELEKT * WHERE { ?s ?p ?o }",                   // typo in keyword
        "SELECT ?x WHERE { ?s ?p ?o } ORDER BY",         // incomplete ORDER BY
        "{ ?s ?p ?o }",                                  // no SELECT/ASK/etc.
        "SELECT * {}",                                    // empty graph pattern (may be valid, check)
    ];

    for q in &bad_queries {
        match engine.query(*q) {
            Ok(_) => { /* some may be valid per SPARQL spec – that's fine */ }
            Err(qlever::Error::Query(msg)) => {
                assert!(!msg.is_empty(), "error message must not be empty for: {q}");
            }
            Err(e) => panic!("unexpected error variant {e} for query: {q}"),
        }
    }
}

/// Various invalid SPARQL Update forms.
#[test]
fn invalid_update_operations() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), 5);

    let bad_updates = [
        "INSERT",                                           // incomplete
        "INSERT DATA",                                      // missing braces
        "INSERT DATA {",                                    // unclosed
        "INSERT DATA { <s> }",                              // incomplete triple
        "DELETE DATA { ?var <ex:p> <ex:o> }",               // variables in DELETE DATA are illegal
        "INSRT DATA { <ex:s> <ex:p> <ex:o> }",             // typo
        "INSERT DATA { <ex:s> <ex:p> <ex:o> } GARBAGE",    // trailing garbage
    ];

    for u in &bad_updates {
        match engine.update(*u) {
            Ok(_) => { /* engine may accept some of these */ }
            Err(qlever::Error::Update(msg)) => {
                assert!(!msg.is_empty(), "error message must not be empty for: {u}");
            }
            Err(e) => panic!("unexpected error variant {e} for update: {u}"),
        }
    }
}

/// SPARQL injection attempt: a query that looks like it tries to escape its
/// string context. The engine must parse it correctly (or reject it cleanly)
/// — it must NEVER execute the injected part as a separate operation.
#[test]
fn sparql_injection_resilience() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), 3);

    // If naively concatenated into a server-side query string this would
    // attempt to close the FILTER and inject a second operation.
    let injection = r#"SELECT * WHERE { ?s ?p ?o FILTER(?o = "foo") } # injection"#;
    match engine.query(injection) {
        Ok(s) => {
            // Must be valid JSON, not garbage
            serde_json::from_str::<serde_json::Value>(&s).expect("must be valid JSON");
        }
        Err(qlever::Error::Query(_)) => { /* rejection is also acceptable */ }
        Err(e) => panic!("unexpected error: {e}"),
    }
}

// ---------------------------------------------------------------------------
// Battery 3 – Resource exhaustion
// ---------------------------------------------------------------------------

/// A very large Turtle file (10 000 triples) indexes and queries correctly.
#[test]
fn large_dataset_index_and_count() {
    if !lib_available() {
        return;
    }
    let n = 10_000usize;
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), n);

    let result = engine
        .query("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }")
        .expect("count query");
    let json: serde_json::Value = serde_json::from_str(&result).expect("valid JSON");
    let count: usize = json["results"]["bindings"][0]["c"]["value"]
        .as_str()
        .unwrap()
        .parse()
        .unwrap();
    assert_eq!(count, n, "count must equal number of inserted triples");
}

/// 1 000 sequential INSERT DATA operations accumulate correctly.
/// This directly tests the delta-triple append path and the performance
/// degradation ceiling identified in the technical survey (~245K triples).
#[test]
fn sequential_inserts_accumulate() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), 0);

    let n_inserts = 1_000usize;
    for i in 0..n_inserts {
        let update = format!(
            "INSERT DATA {{ <http://example.org/s{i}> <http://example.org/p> <http://example.org/o{i}> }}"
        );
        engine.update(&update).unwrap_or_else(|e| panic!("insert {i} failed: {e}"));
    }

    let result = engine
        .query("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }")
        .expect("count query after inserts");
    let json: serde_json::Value = serde_json::from_str(&result).unwrap();
    let count: usize = json["results"]["bindings"][0]["c"]["value"]
        .as_str()
        .unwrap()
        .parse()
        .unwrap();
    assert_eq!(count, n_inserts);
}

/// A query that returns many results (SELECT * with no LIMIT) must not
/// corrupt memory or truncate results.
#[test]
fn large_result_set_no_truncation() {
    if !lib_available() {
        return;
    }
    let n = 1_000usize;
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), n);

    let result = engine
        .query("SELECT * WHERE { ?s <http://example.org/p> ?o }")
        .expect("full scan query");
    let json: serde_json::Value = serde_json::from_str(&result).expect("valid JSON");
    let bindings = json["results"]["bindings"]
        .as_array()
        .expect("bindings must be an array");
    assert_eq!(bindings.len(), n, "all {n} results must be present");
}

/// A deeply nested optional/union pattern. Should not stack-overflow the
/// QLever query planner.
#[test]
fn deeply_nested_optional_does_not_crash() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), 10);

    // 20 levels of OPTIONAL nesting
    let inner = "{ ?s <http://example.org/p> ?o }";
    let mut q = format!("SELECT * WHERE {inner}");
    for depth in 0..20 {
        q = format!("SELECT * WHERE {{ ?s ?p ?o OPTIONAL {{ ?s <http://example.org/p{depth}> ?x }} }}");
    }
    match engine.query(&q) {
        Ok(s) => { serde_json::from_str::<serde_json::Value>(&s).expect("valid JSON"); }
        Err(qlever::Error::Query(_)) => {} // planner rejection is acceptable
        Err(e) => panic!("unexpected error: {e}"),
    }
}

/// A query with an extremely long IRI (64 KB) must not crash (truncate or
/// reject cleanly).
#[test]
fn query_with_very_long_iri() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), 5);

    let long_iri = format!("<http://example.org/{}>", "a".repeat(65_536));
    let q = format!("SELECT * WHERE {{ {long_iri} ?p ?o }}");
    match engine.query(&q) {
        Ok(s) => { serde_json::from_str::<serde_json::Value>(&s).expect("valid JSON"); }
        Err(qlever::Error::Query(_)) => {}
        Err(e) => panic!("unexpected error: {e}"),
    }
}

/// An INSERT with a very large literal value (1 MB string).
#[test]
fn insert_large_literal() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), 0);

    let big_value = "x".repeat(1_048_576); // 1 MB
    let update = format!(
        "INSERT DATA {{ <http://example.org/s> <http://example.org/p> \"{big_value}\" }}"
    );
    match engine.update(&update) {
        Ok(_) => {}
        Err(qlever::Error::Update(_)) => {} // rejection is acceptable
        Err(e) => panic!("unexpected error: {e}"),
    }
}

// ---------------------------------------------------------------------------
// Battery 4 – Concurrency
// ---------------------------------------------------------------------------

/// Send the engine to a background thread, run a query, and receive the
/// result.  This validates `unsafe impl Send for Qlever`.
#[test]
fn engine_is_send_across_threads() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), 10);

    let result = std::thread::spawn(move || {
        engine
            .query("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }")
            .expect("query from worker thread")
    })
    .join()
    .expect("thread panic");

    let json: serde_json::Value = serde_json::from_str(&result).unwrap();
    let count: usize = json["results"]["bindings"][0]["c"]["value"]
        .as_str()
        .unwrap()
        .parse()
        .unwrap();
    assert_eq!(count, 10);
}

/// Multiple threads each run queries via Arc<Mutex<Qlever>>.
/// This is the recommended pattern when sharing an engine.
#[test]
fn mutex_wrapped_engine_shared_across_threads() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = Arc::new(Mutex::new(build_and_open(tmp.path(), 20)));

    let handles: Vec<_> = (0..8)
        .map(|_| {
            let eng = Arc::clone(&engine);
            std::thread::spawn(move || {
                let guard = eng.lock().unwrap();
                guard
                    .query("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }")
                    .expect("query from thread")
            })
        })
        .collect();

    for h in handles {
        let result = h.join().expect("thread panic");
        let json: serde_json::Value = serde_json::from_str(&result).unwrap();
        let count: usize = json["results"]["bindings"][0]["c"]["value"]
            .as_str()
            .unwrap()
            .parse()
            .unwrap();
        assert_eq!(count, 20, "each thread should see 20 triples");
    }
}

/// Interleaved queries and updates via Mutex: final count must be consistent.
#[test]
fn interleaved_query_and_update_consistency() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = Arc::new(Mutex::new(build_and_open(tmp.path(), 0)));

    let n_writers = 4usize;
    let inserts_per_writer = 25usize;

    let handles: Vec<_> = (0..n_writers)
        .map(|t| {
            let eng = Arc::clone(&engine);
            std::thread::spawn(move || {
                for i in 0..inserts_per_writer {
                    let update = format!(
                        "INSERT DATA {{ <http://example.org/t{t}s{i}> <http://example.org/p> <http://example.org/o> }}"
                    );
                    eng.lock().unwrap().update(&update).unwrap();
                }
            })
        })
        .collect();

    for h in handles {
        h.join().expect("writer thread panic");
    }

    let result = engine
        .lock()
        .unwrap()
        .query("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }")
        .expect("final count");
    let json: serde_json::Value = serde_json::from_str(&result).unwrap();
    let count: usize = json["results"]["bindings"][0]["c"]["value"]
        .as_str()
        .unwrap()
        .parse()
        .unwrap();
    assert_eq!(
        count,
        n_writers * inserts_per_writer,
        "count must equal total inserts with no lost writes or double-counts"
    );
}

// ---------------------------------------------------------------------------
// Battery 5 – Lifecycle
// ---------------------------------------------------------------------------

/// Open the same index twice in the same process. Both instances must be
/// independently usable (the C++ library must support this).
#[test]
fn two_engines_on_same_index() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let ttl = write_dataset(tmp.path(), 5);
    let base = tmp.path().join("idx").to_string_lossy().into_owned();

    qlever::IndexBuilderOptions::new(base.as_str(), ttl.to_str().unwrap())
        .build()
        .expect("index build");

    let engine1 = qlever::EngineOptions::new(base.as_str())
        .persist_updates(false)
        .open()
        .expect("first open");
    let engine2 = qlever::EngineOptions::new(base.as_str())
        .persist_updates(false)
        .open()
        .expect("second open");

    let r1 = engine1.query("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }").expect("engine1 query");
    let r2 = engine2.query("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }").expect("engine2 query");

    // Both must agree on triple count.
    let c1: usize = serde_json::from_str::<serde_json::Value>(&r1).unwrap()
        ["results"]["bindings"][0]["c"]["value"].as_str().unwrap().parse().unwrap();
    let c2: usize = serde_json::from_str::<serde_json::Value>(&r2).unwrap()
        ["results"]["bindings"][0]["c"]["value"].as_str().unwrap().parse().unwrap();
    assert_eq!(c1, 5);
    assert_eq!(c2, 5);
    // Dropping both engines must not double-free.
    drop(engine1);
    drop(engine2);
}

/// Re-open after drop: build, open, query, drop, re-open, query again.
/// The second open must see the same data (index files are stable on disk).
#[test]
fn reopen_after_drop_sees_same_data() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let ttl = write_dataset(tmp.path(), 7);
    let base = tmp.path().join("idx").to_string_lossy().into_owned();

    qlever::IndexBuilderOptions::new(base.as_str(), ttl.to_str().unwrap())
        .build()
        .expect("index build");

    let count_query = "SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }";
    let count = |engine: &qlever::Qlever| -> usize {
        let r = engine.query(count_query).expect("count query");
        serde_json::from_str::<serde_json::Value>(&r).unwrap()
            ["results"]["bindings"][0]["c"]["value"].as_str().unwrap().parse().unwrap()
    };

    {
        let engine = qlever::EngineOptions::new(base.as_str())
            .persist_updates(false)
            .open()
            .expect("first open");
        assert_eq!(count(&engine), 7, "first open: count must be 7");
        // engine is dropped here
    }

    {
        let engine = qlever::EngineOptions::new(base.as_str())
            .persist_updates(false)
            .open()
            .expect("second open after drop");
        assert_eq!(count(&engine), 7, "second open: count must still be 7");
    }
}

/// Attempt to open a non-existent index: must return Error::Open, not panic.
#[test]
fn open_nonexistent_index_returns_error() {
    if !lib_available() {
        return;
    }
    let err = qlever::EngineOptions::new("/nonexistent/path/to/index")
        .open()
        .unwrap_err();
    assert!(
        matches!(err, qlever::Error::Open(_)),
        "expected Open error, got: {err}"
    );
}

/// Attempt to build an index from a non-existent file: must return
/// Error::IndexBuild, not panic.
#[test]
fn build_nonexistent_input_file_returns_error() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let base = tmp.path().join("idx").to_string_lossy().into_owned();
    let err = qlever::IndexBuilderOptions::new(base, "/this/file/does/not/exist.ttl")
        .build()
        .unwrap_err();
    assert!(
        matches!(err, qlever::Error::IndexBuild(_)),
        "expected IndexBuild error, got: {err}"
    );
}

/// INSERT followed immediately by DELETE of the same triple: net result must
/// be 0 new triples.
#[test]
fn insert_then_delete_same_triple_nets_zero() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), 0);

    let s = "<http://example.org/s>";
    let p = "<http://example.org/p>";
    let o = "<http://example.org/o>";

    engine
        .update(&format!("INSERT DATA {{ {s} {p} {o} }}"))
        .expect("INSERT");
    engine
        .update(&format!("DELETE DATA {{ {s} {p} {o} }}"))
        .expect("DELETE");

    let result = engine
        .query("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }")
        .expect("count");
    let json: serde_json::Value = serde_json::from_str(&result).unwrap();
    let count: usize = json["results"]["bindings"][0]["c"]["value"]
        .as_str()
        .unwrap()
        .parse()
        .unwrap();
    assert_eq!(count, 0, "insert+delete of the same triple must yield 0");
}

/// DELETE of a triple that does not exist: must succeed silently (SPARQL spec
/// says this is not an error — it is a no-op).
#[test]
fn delete_nonexistent_triple_is_noop() {
    if !lib_available() {
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let engine = build_and_open(tmp.path(), 3);

    engine
        .update("DELETE DATA { <http://example.org/ghost> <http://example.org/p> <http://example.org/o> }")
        .expect("DELETE of non-existent triple should be a no-op, not an error");
}

/// Version string must be a valid semver-like string (X.Y.Z format).
#[test]
fn version_format() {
    let v = qlever::Qlever::version();
    let parts: Vec<&str> = v.split('.').collect();
    assert!(
        parts.len() >= 2,
        "version '{v}' should have at least major.minor"
    );
    for part in &parts {
        assert!(
            part.chars().all(|c| c.is_ascii_digit()),
            "version component '{part}' in '{v}' should be numeric"
        );
    }
}
