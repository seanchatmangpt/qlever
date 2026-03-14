// Copyright 2025 The QLever Authors, in particular:
//
// 2025 Johannes Kalmbach <kalmbach@cs.uni-freiburg.de>, UFR
//
// UFR = University of Freiburg, Chair of Algorithms and Data Structures

// C shim for the QLever embedded C++ API.
//
// This header exposes a pure-C interface so that external languages (Rust,
// Python, Go, …) can link against QLever via a stable ABI without exposing
// C++ name-mangling or exceptions across the language boundary.
//
// Ownership rules
// ---------------
//   * Every `char *` returned by this API is heap-allocated with `malloc`.
//     Callers **must** free it with `qlever_free_string()`; do NOT use the
//     system `free()` directly (the allocator may differ across DLL
//     boundaries on some platforms).
//   * `QleverHandle` objects are opaque; obtain them with `qlever_create` and
//     release them with `qlever_destroy`.
//
// Error handling
// --------------
//   * Functions that can fail return an `int`:  0 = success, non-zero = error.
//   * On error the last error message can be retrieved with
//     `qlever_last_error()`.  The returned string is thread-local and
//     overwritten on the next error in the same thread; copy it if you need
//     it beyond the next call.

#ifndef QLEVER_SRC_LIBQLEVER_QLEVER_C_H
#define QLEVER_SRC_LIBQLEVER_QLEVER_C_H

#include <stddef.h>  // size_t

#ifdef __cplusplus
extern "C" {
#endif

// ---------------------------------------------------------------------------
// Opaque handle to a live QLever instance (loaded index + query engine).
// ---------------------------------------------------------------------------
typedef struct QleverHandle QleverHandle;

// ---------------------------------------------------------------------------
// Index building
// ---------------------------------------------------------------------------

// Build a QLever RDF index from a single Turtle/N-Triples/N-Quads input file.
//
// Parameters
//   base_name      – basename for all index files written to disk
//                    (e.g. "/tmp/myindex/mydata")
//   input_file     – path to the RDF input file
//   memory_limit_gb – upper memory bound in gigabytes (0 = default 1 GB)
//
// Returns 0 on success, non-zero on failure.
// Call `qlever_last_error()` for the error message.
int qlever_build_index(const char* base_name, const char* input_file,
                       double memory_limit_gb);

// ---------------------------------------------------------------------------
// Engine lifecycle
// ---------------------------------------------------------------------------

// Load a previously built index and return a handle to the query engine.
//
// Parameters
//   base_name       – same basename used when building the index
//   memory_limit_gb – upper memory bound in gigabytes (0 = default 1 GB)
//   persist_updates – if non-zero, SPARQL updates are persisted to
//                     `base_name.update-triples` so they survive restarts
//
// Returns a valid handle on success, NULL on failure.
// Call `qlever_last_error()` for the error message.
QleverHandle* qlever_create(const char* base_name, double memory_limit_gb,
                            int persist_updates);

// Destroy a handle and free all associated resources.
// Passing NULL is a no-op.
void qlever_destroy(QleverHandle* handle);

// ---------------------------------------------------------------------------
// SPARQL query execution
// ---------------------------------------------------------------------------

// Execute a SPARQL SELECT/ASK/CONSTRUCT/DESCRIBE query.
//
// Returns a heap-allocated, NUL-terminated JSON string on success, or NULL on
// failure.  The caller must free the result with `qlever_free_string()`.
//
// The result format is W3C SPARQL JSON (application/sparql-results+json) by
// default.
char* qlever_query(const QleverHandle* handle, const char* sparql);

// ---------------------------------------------------------------------------
// SPARQL 1.1 Update
// ---------------------------------------------------------------------------

// Execute a SPARQL 1.1 Update operation (INSERT DATA, DELETE DATA,
// INSERT/DELETE WHERE, LOAD, CLEAR, …).
//
// Returns a heap-allocated JSON string containing per-operation metadata
// (inserted/deleted triple counts) on success, or NULL on failure.
// The caller must free the result with `qlever_free_string()`.
char* qlever_update(QleverHandle* handle, const char* sparql_update);

// ---------------------------------------------------------------------------
// Memory management helpers
// ---------------------------------------------------------------------------

// Free a string returned by `qlever_query` or `qlever_update`.
void qlever_free_string(char* str);

// ---------------------------------------------------------------------------
// Error reporting
// ---------------------------------------------------------------------------

// Return a human-readable description of the last error that occurred in the
// calling thread.  The pointer is valid until the next qlever_* call in the
// same thread (or the thread exits).  Never NULL.
const char* qlever_last_error(void);

// Return the QLever library version string (e.g. "0.5.45").
// The returned pointer is static and must NOT be freed.
const char* qlever_version(void);

#ifdef __cplusplus
}  // extern "C"
#endif

#endif  // QLEVER_SRC_LIBQLEVER_QLEVER_C_H
