use std::path::PathBuf;

#[test]
fn native_qlever_library_is_present_at_runtime() {
    let lib_dir = std::env::var("QLEVER_LIB_DIR")
        .expect("QLEVER_LIB_DIR must be set; native FFI tests may not pass vacuously");
    let lib_dir = PathBuf::from(lib_dir);
    assert!(
        lib_dir.is_dir(),
        "QLEVER_LIB_DIR is not a directory: {}",
        lib_dir.display()
    );

    let candidates = ["libqlever_c.so", "libqlever_c.dylib", "qlever_c.dll"];
    assert!(
        candidates.iter().any(|name| lib_dir.join(name).is_file()),
        "QLEVER_LIB_DIR does not contain a qlever_c shared library: {}",
        lib_dir.display()
    );
}
