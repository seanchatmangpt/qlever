use std::env;
use std::path::PathBuf;

fn main() {
    println!("cargo:rerun-if-changed=../../src/libqlever/qlever_c.h");
    println!("cargo:rerun-if-env-changed=QLEVER_LIB_DIR");

    let lib_dir = PathBuf::from(
        env::var("QLEVER_LIB_DIR")
            .expect("QLEVER_LIB_DIR must point to the directory containing libqlever_c"),
    );
    assert!(
        lib_dir.is_dir(),
        "QLEVER_LIB_DIR is not a directory: {}",
        lib_dir.display()
    );

    // The C shim is a shared library because it already carries the complete
    // native QLever link closure. Linking the standalone static archive here
    // leaves QLever's transitive C++ symbols unresolved in Rust binaries.
    println!("cargo:rustc-link-search=native={}", lib_dir.display());
    println!("cargo:rustc-link-lib=dylib=qlever_c");

    let header = PathBuf::from("../../src/libqlever/qlever_c.h");
    let bindings = bindgen::Builder::default()
        .header(header.to_string_lossy())
        .allowlist_function("qlever_.*")
        .allowlist_type("QleverHandle")
        .generate()
        .expect("failed to generate qlever C bindings");

    let out_path = PathBuf::from(env::var("OUT_DIR").expect("Cargo did not set OUT_DIR"));
    bindings
        .write_to_file(out_path.join("bindings.rs"))
        .expect("failed to write qlever bindings");
}
