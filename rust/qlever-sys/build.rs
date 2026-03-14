// build.rs for qlever-sys
//
// This script does three things:
//
//  1. Invokes `bindgen` to generate raw Rust FFI declarations from the
//     `qlever_c.h` header.  The generated file lands in OUT_DIR/bindings.rs.
//
//  2. Tells Cargo where to find the pre-built C shim library (`libqlever_c`)
//     via the `QLEVER_LIB_DIR` environment variable, which must point to the
//     CMake build directory containing libqlever_c.a (or .so).
//
//  3. Links the host C++ standard library so that the Rust linker can resolve
//     the C++ symbols pulled in transitively through libqlever_c.
//
// Environment variables consumed by this script
// -----------------------------------------------
//   QLEVER_LIB_DIR    Directory containing libqlever_c.a / libqlever_c.so
//                     (required; no default)
//   QLEVER_INCLUDE_DIR  Directory containing qlever_c.h
//                     (default: ../../../src/libqlever relative to this file)
//
// Example (from the workspace root after building QLever with CMake):
//
//   QLEVER_LIB_DIR=/path/to/build/src/libqlever \
//   cargo build -p qlever-sys

use std::{env, path::PathBuf};

fn main() {
    // ------------------------------------------------------------------
    // 1.  Locate the header and library
    // ------------------------------------------------------------------
    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap());

    let include_dir = env::var("QLEVER_INCLUDE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| manifest_dir.join("../../..").join("src/libqlever"));

    let header = include_dir.join("qlever_c.h");

    let lib_dir = env::var("QLEVER_LIB_DIR").expect(
        "QLEVER_LIB_DIR must be set to the directory containing libqlever_c.a\n\
         Build QLever with CMake first, then re-run `cargo build`.",
    );

    // ------------------------------------------------------------------
    // 2.  Tell Cargo how to link
    // ------------------------------------------------------------------
    println!("cargo:rustc-link-search=native={lib_dir}");
    // Prefer static linking to avoid runtime .so path issues.
    println!("cargo:rustc-link-lib=static=qlever_c");

    // Link the C++ standard library (g++/clang++ style).
    // On macOS use libc++ (clang default); on Linux use libstdc++.
    #[cfg(target_os = "macos")]
    println!("cargo:rustc-link-lib=c++");
    #[cfg(not(target_os = "macos"))]
    println!("cargo:rustc-link-lib=stdc++");

    // Rerun if the header or this script changes.
    println!("cargo:rerun-if-changed=build.rs");
    println!(
        "cargo:rerun-if-changed={}",
        header.display()
    );
    println!("cargo:rerun-if-env-changed=QLEVER_LIB_DIR");
    println!("cargo:rerun-if-env-changed=QLEVER_INCLUDE_DIR");

    // ------------------------------------------------------------------
    // 3.  Generate bindings with bindgen
    // ------------------------------------------------------------------
    let bindings = bindgen::Builder::default()
        .header(header.to_str().expect("non-UTF-8 header path"))
        // Only generate bindings for the public qlever_c API.
        .allowlist_function("qlever_.*")
        .allowlist_type("QleverHandle")
        // We only need C-compatible types; block everything else.
        .blocklist_type("__.*")
        // Use core:: types rather than std:: so the crate works in no_std.
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
