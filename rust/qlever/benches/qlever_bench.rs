// qlever_bench.rs – micro and macro benchmarks for the QLever Rust FFI.
//
// Run with:
//   QLEVER_LIB_DIR=... cargo bench -p qlever
//
// What we measure (in order of interest):
//
//  1. cold_query          – first query after index load (incl. warm-up cost)
//  2. hot_query_count     – COUNT(*) on a warm index (cache hot)
//  3. hot_query_full_scan – SELECT * with no LIMIT on a 1 000-triple index
//  4. insert_single       – latency of one INSERT DATA operation
//  5. insert_batch        – latency of one INSERT DATA with 100 triples
//  6. index_build_small   – time to build a 1 000-triple index from scratch
//  7. open_engine         – time to load a pre-built index
//
// All benchmarks skip themselves when QLEVER_LIB_DIR is not set.

use std::hint::black_box;
use std::time::{Duration, Instant};

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

fn lib_available() -> bool {
    std::env::var("QLEVER_LIB_DIR").is_ok()
}

fn write_dataset(dir: &std::path::Path, n: usize) -> std::path::PathBuf {
    use std::fmt::Write as _;
    let path = dir.join("data.ttl");
    let mut ttl = String::from("@prefix ex: <http://example.org/> .\n");
    for i in 0..n {
        writeln!(ttl, "ex:s{i} <http://example.org/p> ex:o{i} .").unwrap();
    }
    std::fs::write(&path, &ttl).expect("write dataset");
    path
}

fn build_index(dir: &std::path::Path, n: usize) -> String {
    let ttl = write_dataset(dir, n);
    let base = dir.join("idx").to_string_lossy().into_owned();
    qlever::IndexBuilderOptions::new(base.as_str(), ttl.to_str().unwrap())
        .memory_limit_gb(1.0)
        .build()
        .expect("index build");
    base
}

fn open_engine(base: &str) -> qlever::Qlever {
    qlever::EngineOptions::new(base)
        .memory_limit_gb(1.0)
        .persist_updates(false)
        .open()
        .expect("engine open")
}

/// Minimal harness: run `f` for `iters` iterations and report mean / min / max.
fn bench<F: FnMut() -> ()>(name: &str, iters: u32, mut f: F) {
    // Warm up
    for _ in 0..3 {
        f();
    }

    let mut times = Vec::with_capacity(iters as usize);
    for _ in 0..iters {
        let t0 = Instant::now();
        f();
        times.push(t0.elapsed());
    }

    times.sort();
    let total: Duration = times.iter().sum();
    let mean = total / iters;
    let min = times[0];
    let max = *times.last().unwrap();
    let p50 = times[iters as usize / 2];
    let p95 = times[(iters as usize * 95) / 100];

    eprintln!(
        "BENCH {name:<35} iters={iters:4}  mean={:>8.3?}  min={:>8.3?}  p50={:>8.3?}  p95={:>8.3?}  max={:>8.3?}",
        mean, min, p50, p95, max,
    );
}

// ---------------------------------------------------------------------------
// Benchmarks
// ---------------------------------------------------------------------------

fn main() {
    if !lib_available() {
        eprintln!("BENCH: QLEVER_LIB_DIR not set – all benchmarks skipped");
        return;
    }

    // ----------------------------------------------------------------
    // Setup shared state outside the timed loops.
    // ----------------------------------------------------------------
    let tmp_build = tempfile::tempdir().unwrap();
    let tmp_open  = tempfile::tempdir().unwrap();
    let tmp_query = tempfile::tempdir().unwrap();
    let tmp_scan  = tempfile::tempdir().unwrap();
    let tmp_ins   = tempfile::tempdir().unwrap();
    let tmp_batch = tempfile::tempdir().unwrap();

    let base_build = build_index(tmp_build.path(), 1_000);
    let base_open  = build_index(tmp_open.path(),  1_000);
    let base_query = build_index(tmp_query.path(), 1_000);
    let base_scan  = build_index(tmp_scan.path(),  1_000);
    let base_ins   = build_index(tmp_ins.path(),   0);
    let base_batch = build_index(tmp_batch.path(), 0);

    let engine_query = open_engine(&base_query);
    let engine_scan  = open_engine(&base_scan);
    let engine_ins   = open_engine(&base_ins);
    let engine_batch = open_engine(&base_batch);

    // ----------------------------------------------------------------
    // 1. cold_query – measure full open + COUNT query + drop in one shot.
    //    Each iteration opens a fresh engine handle (index files already built).
    // ----------------------------------------------------------------
    bench("cold_query", 20, || {
        let e = open_engine(black_box(&base_open));
        let r = e.query("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }").unwrap();
        black_box(r);
        drop(e);
    });

    // ----------------------------------------------------------------
    // 2. hot_query_count – COUNT on a warm (cached) engine.
    // ----------------------------------------------------------------
    bench("hot_query_count", 200, || {
        let r = engine_query
            .query(black_box("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }"))
            .unwrap();
        black_box(r);
    });

    // ----------------------------------------------------------------
    // 3. hot_query_full_scan – SELECT * (1 000 results).
    // ----------------------------------------------------------------
    bench("hot_query_full_scan_1k", 50, || {
        let r = engine_scan
            .query(black_box("SELECT * WHERE { ?s ?p ?o }"))
            .unwrap();
        black_box(r);
    });

    // ----------------------------------------------------------------
    // 4. insert_single – latency of one INSERT DATA (single triple).
    //    Each iteration inserts a unique triple to avoid duplicate detection.
    // ----------------------------------------------------------------
    let mut ins_counter = 0u64;
    bench("insert_single", 200, || {
        let n = ins_counter;
        ins_counter += 1;
        let u = format!(
            "INSERT DATA {{ <http://example.org/s{n}> <http://example.org/p> <http://example.org/o{n}> }}"
        );
        engine_ins.update(black_box(&u)).unwrap();
    });

    // ----------------------------------------------------------------
    // 5. insert_batch – one INSERT DATA containing 100 triples.
    // ----------------------------------------------------------------
    let mut batch_counter = 0u64;
    bench("insert_batch_100", 50, || {
        use std::fmt::Write as _;
        let base_n = batch_counter * 100;
        batch_counter += 1;
        let mut upd = String::from("INSERT DATA {\n");
        for i in 0..100u64 {
            writeln!(
                upd,
                "  <http://example.org/s{}> <http://example.org/p> <http://example.org/o{}> .",
                base_n + i,
                base_n + i,
            )
            .unwrap();
        }
        upd.push('}');
        engine_batch.update(black_box(&upd)).unwrap();
    });

    // ----------------------------------------------------------------
    // 6. index_build_small – build a 1 000-triple index from scratch.
    //    Each iteration uses a fresh tempdir to avoid file conflicts.
    //    (Expensive; only 5 iterations.)
    // ----------------------------------------------------------------
    bench("index_build_1k_triples", 5, || {
        let t = tempfile::tempdir().unwrap();
        let ttl = write_dataset(t.path(), 1_000);
        let base = t.path().join("idx").to_string_lossy().into_owned();
        qlever::IndexBuilderOptions::new(black_box(base.as_str()), ttl.to_str().unwrap())
            .memory_limit_gb(1.0)
            .build()
            .unwrap();
    });

    // ----------------------------------------------------------------
    // 7. open_engine – time to load a pre-built 1 000-triple index.
    // ----------------------------------------------------------------
    bench("open_engine_1k", 20, || {
        let e = open_engine(black_box(&base_build));
        black_box(&e);
        drop(e);
    });

    eprintln!("BENCH: complete");
}
