// build.rs for qlever-sys
//
// This script does three things:
//
//  1. Invokes `bindgen` to generate raw Rust FFI declarations from the
//     `qlever_c.h` header. The generated file lands in OUT_DIR/bindings.rs.
//
//  2. Tells Cargo where to find the pre-built C shim shared library
//     (`libqlever_c`) via the `QLEVER_LIB_DIR` environment variable.
//
//  3. Keeps the native include and library locations explicit and replayable;
//     there is no fallback to a system-installed QLever.
//
// Environment variables consumed by this script
// -----------------------------------------------
//   QLEVER_LIB_DIR      Directory containing libqlever_c.so / .dylib / .dll
//                       (required; no default)
//   QLEVER_INCLUDE_DIR  Directory containing qlever_c.h
//                       (default: ../../src/libqlever from this crate)
//
// Example (from the workspace root after building QLever with CMake):
//
//   QLEVER_LIB_DIR=/path/to/build/src/libqlever \
//   cargo build -p qlever-sys

use std::{env, path::PathBuf};

fn main() {
    // ------------------------------------------------------------------
    // 1. Locate the header and library
    // ------------------------------------------------------------------
    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap());

    let include_dir = env::var("QLEVER_INCLUDE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| manifest_dir.join("../..").join("src/libqlever"));

    let header = include_dir.join("qlever_c.h");
    assert!(
        header.is_file(),
        "qlever_c.h not found at {}; set QLEVER_INCLUDE_DIR explicitly if using a non-repository layout",
        header.display()
    );

    let lib_dir = PathBuf::from(env::var("QLEVER_LIB_DIR").expect(
        "QLEVER_LIB_DIR must be set to the directory containing the qlever_c shared library\n\
         Build the qlever_c CMake target first, then re-run `cargo build`.",
    ));
    assert!(
        lib_dir.is_dir(),
        "QLEVER_LIB_DIR is not a directory: {}",
        lib_dir.display()
    );

    // ------------------------------------------------------------------
    // 2. Tell Cargo how to link
    // ------------------------------------------------------------------
    // qlever_c is intentionally linked dynamically. Its shared-library link
    // step closes over the native QLever/C++ dependency graph; linking only the
    // standalone static qlever_c archive from Rust leaves transitive QLever
    // symbols unresolved.
    println!("cargo:rustc-link-search=native={}", lib_dir.display());
    println!("cargo:rustc-link-lib=dylib=qlever_c");

    // Rerun if the header, this script, or admitted native locations change.
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-changed={}", header.display());
    println!("cargo:rerun-if-env-changed=QLEVER_LIB_DIR");
    println!("cargo:rerun-if-env-changed=QLEVER_INCLUDE_DIR");

    // ------------------------------------------------------------------
    // 3. Generate bindings with bindgen
    // ------------------------------------------------------------------
    let bindings = bindgen::Builder::default()
        .header(header.to_str().expect("non-UTF-8 header path"))
        // Only generate bindings for the public qlever_c API.
        .allowlist_function("qlever_.*")
        .allowlist_type("QleverHandle")
        // We only need C-compatible types; block everything else.
        .blocklist_type("__.*")
        // Use core:: types rather than std:: so the generated declarations
        // remain usable by no_std consumers of qlever-sys.
        .use_core()
        // Derive common traits automatically.
        .derive_debug(true)
        .derive_copy(true)
        .derive_default(false)
        // Silence warnings about non-Rust naming conventions in generated code.
        .raw_line("#![allow(non_upper_case_globals)]")
        .raw_line("#![allow(non_camel_case_types)]")
        .raw_line("#![allow(non_snake_case)]")
        .raw_line("#![allow(dead_code)]")
        .parse_callbacks(Box::new(bindgen::CargoCallbacks::new()))
        .generate()
        .expect("bindgen failed to generate FFI bindings");

    let out_dir = PathBuf::from(env::var("OUT_DIR").unwrap());
    bindings
        .write_to_file(out_dir.join("bindings.rs"))
        .expect("failed to write bindings.rs");
}
