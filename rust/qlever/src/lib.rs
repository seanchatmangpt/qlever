// qlever: safe Rust bindings for the QLever embedded SPARQL engine.
//
// # Quick start
//
// ```rust,no_run
// use qlever::{Qlever, IndexBuilderOptions, EngineOptions};
//
// // 1. Build an index from a Turtle file (one-time setup).
// IndexBuilderOptions::new("/tmp/mydata", "/path/to/data.ttl")
//     .build()
//     .expect("index build failed");
//
// // 2. Load the index and run a SPARQL query.
// let engine = EngineOptions::new("/tmp/mydata")
//     .open()
//     .expect("failed to open engine");
//
// let result = engine.query("SELECT * WHERE { ?s ?p ?o } LIMIT 10")
//     .expect("query failed");
// println!("{result}");
//
// // 3. Apply a SPARQL Update.
// engine.update("INSERT DATA { <ex:s> <ex:p> <ex:o> }")
//     .expect("update failed");
// ```

mod error;
pub use error::{Error, Result};

use std::ffi::{CStr, CString};
use std::os::raw::c_char;
use std::ptr::NonNull;

use qlever_sys as sys;

// ---------------------------------------------------------------------------
// IndexBuilderOptions
// ---------------------------------------------------------------------------

/// Configuration for building a QLever RDF index from a file on disk.
///
/// Call [`IndexBuilderOptions::build`] to actually create the index files.
pub struct IndexBuilderOptions {
    base_name: CString,
    input_file: CString,
    memory_limit_gb: f64,
}

impl IndexBuilderOptions {
    /// Create a new builder configuration.
    ///
    /// * `base_name`  – basename for all index files (e.g. `"/tmp/myidx/data"`)
    /// * `input_file` – path to a Turtle, N-Triples, or N-Quads RDF file
    pub fn new(base_name: impl Into<Vec<u8>>, input_file: impl Into<Vec<u8>>) -> Self {
        Self {
            base_name: CString::new(base_name).expect("base_name contains NUL byte"),
            input_file: CString::new(input_file).expect("input_file contains NUL byte"),
            memory_limit_gb: 0.0,
        }
    }

    /// Set an upper bound on the memory QLever may use during index building.
    ///
    /// The value is in gigabytes.  Pass `0.0` (the default) to use QLever's
    /// internal default of 1 GB.
    pub fn memory_limit_gb(mut self, gb: f64) -> Self {
        self.memory_limit_gb = gb;
        self
    }

    /// Build the index.
    ///
    /// This writes permutation files and vocabulary structures to disk under
    /// the path prefix given by `base_name`.  The call blocks until the full
    /// index has been written.
    ///
    /// # Errors
    ///
    /// Returns [`Error::IndexBuild`] if QLever reports an error.
    pub fn build(self) -> Result<()> {
        let rc = unsafe {
            sys::qlever_build_index(
                self.base_name.as_ptr(),
                self.input_file.as_ptr(),
                self.memory_limit_gb,
            )
        };
        if rc == 0 {
            Ok(())
        } else {
            Err(Error::IndexBuild(last_error()))
        }
    }
}

// ---------------------------------------------------------------------------
// EngineOptions
// ---------------------------------------------------------------------------

/// Configuration for opening an existing QLever index for query execution.
///
/// Call [`EngineOptions::open`] to obtain a [`Qlever`] instance.
pub struct EngineOptions {
    base_name: CString,
    memory_limit_gb: f64,
    persist_updates: bool,
}

impl EngineOptions {
    /// Create a new engine configuration.
    ///
    /// * `base_name` – the same basename that was used when building the index
    pub fn new(base_name: impl Into<Vec<u8>>) -> Self {
        Self {
            base_name: CString::new(base_name).expect("base_name contains NUL byte"),
            memory_limit_gb: 0.0,
            persist_updates: true,
        }
    }

    /// Set an upper bound on the memory QLever may use during query execution.
    ///
    /// The value is in gigabytes.  Pass `0.0` (the default) to use QLever's
    /// internal default of 1 GB.
    pub fn memory_limit_gb(mut self, gb: f64) -> Self {
        self.memory_limit_gb = gb;
        self
    }

    /// Control whether SPARQL Updates are persisted to a `.update-triples`
    /// delta file on disk.
    ///
    /// When `true` (the default), updates survive a process restart.  Set to
    /// `false` for read-only workloads or when persistence is managed
    /// externally.
    pub fn persist_updates(mut self, persist: bool) -> Self {
        self.persist_updates = persist;
        self
    }

    /// Open the index and return a [`Qlever`] engine handle.
    ///
    /// # Errors
    ///
    /// Returns [`Error::Open`] if QLever cannot load the index (e.g., the
    /// index files are missing or corrupted).
    pub fn open(self) -> Result<Qlever> {
        let raw = unsafe {
            sys::qlever_create(
                self.base_name.as_ptr(),
                self.memory_limit_gb,
                self.persist_updates as i32,
            )
        };
        match NonNull::new(raw) {
            Some(ptr) => Ok(Qlever { ptr }),
            None => Err(Error::Open(last_error())),
        }
    }
}

// ---------------------------------------------------------------------------
// Qlever engine handle
// ---------------------------------------------------------------------------

/// An open QLever index ready for SPARQL query and update execution.
///
/// Obtain a `Qlever` instance via [`EngineOptions::open`].
///
/// # Thread safety
///
/// `Qlever` is `Send` but not `Sync`.  The underlying C++ engine uses
/// thread-safe internal caches, but the handle itself must not be shared
/// across threads concurrently without external synchronisation (e.g., a
/// `Mutex<Qlever>`).
pub struct Qlever {
    ptr: NonNull<sys::QleverHandle>,
}

// SAFETY: The C++ Qlever class is designed to be used from a single thread at
// a time.  Wrapping in Mutex<Qlever> is the caller's responsibility when
// multi-threaded access is needed.
unsafe impl Send for Qlever {}

impl Drop for Qlever {
    fn drop(&mut self) {
        unsafe { sys::qlever_destroy(self.ptr.as_ptr()) };
    }
}

impl Qlever {
    /// Execute a SPARQL SELECT / ASK / CONSTRUCT / DESCRIBE query.
    ///
    /// Returns the result as a W3C SPARQL JSON string
    /// (`application/sparql-results+json`).
    ///
    /// # Errors
    ///
    /// Returns [`Error::Query`] if the query is malformed or execution fails.
    pub fn query(&self, sparql: impl Into<Vec<u8>>) -> Result<String> {
        let q = CString::new(sparql).map_err(|_| Error::NulByte)?;
        // SAFETY: qlever_query takes *const QleverHandle; cast *mut → *const.
        let raw = unsafe { sys::qlever_query(self.ptr.as_ptr() as *const _, q.as_ptr()) };
        cstring_result_to_rust(raw, Error::Query)
    }

    /// Execute a SPARQL 1.1 Update operation.
    ///
    /// Supported update forms: `INSERT DATA`, `DELETE DATA`,
    /// `INSERT/DELETE WHERE`, `LOAD`, `CLEAR`, and graph management
    /// operations.
    ///
    /// Returns a JSON string containing per-operation metadata (the number of
    /// triples inserted and deleted).
    ///
    /// # Errors
    ///
    /// Returns [`Error::Update`] if the update is malformed or execution fails.
    pub fn update(&self, sparql_update: impl Into<Vec<u8>>) -> Result<String> {
        let q = CString::new(sparql_update).map_err(|_| Error::NulByte)?;
        // qlever_update takes *mut QleverHandle (non-const: updates mutate state).
        let raw = unsafe { sys::qlever_update(self.ptr.as_ptr(), q.as_ptr()) };
        cstring_result_to_rust(raw, Error::Update)
    }

    /// Return the QLever library version string (e.g. `"0.5.45"`).
    pub fn version() -> &'static str {
        // SAFETY: qlever_version returns a static NUL-terminated string.
        unsafe { CStr::from_ptr(sys::qlever_version()) }
            .to_str()
            .unwrap_or("unknown")
    }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/// Retrieve the last QLever error as an owned `String`.
fn last_error() -> String {
    // SAFETY: qlever_last_error always returns a valid, NUL-terminated,
    // thread-local string.  It is valid until the next qlever_* call on this
    // thread, and we copy it immediately.
    let ptr = unsafe { sys::qlever_last_error() };
    unsafe { CStr::from_ptr(ptr) }
        .to_str()
        .unwrap_or("error message is not valid UTF-8")
        .to_owned()
}

/// Convert a `malloc`-allocated `char *` result into a Rust `String`, or map
/// `NULL` to an `Err` by calling `last_error()`.
///
/// The pointer is freed via `qlever_free_string` once copied.
fn cstring_result_to_rust(raw: *mut c_char, make_err: impl FnOnce(String) -> Error) -> Result<String> {
    if raw.is_null() {
        return Err(make_err(last_error()));
    }
    // SAFETY: `raw` is a malloc-allocated, NUL-terminated C string.
    let s = unsafe { CStr::from_ptr(raw) }
        .to_str()
        .map(str::to_owned)
        .map_err(|_| Error::Utf8);
    unsafe { sys::qlever_free_string(raw) };
    s
}
