// Error types for the `qlever` safe Rust wrapper.

use std::fmt;

/// The error type returned by all fallible `qlever` API calls.
#[derive(Debug)]
pub enum Error {
    /// Failed to build a QLever index.  The inner string contains the
    /// human-readable error message reported by the C++ library.
    IndexBuild(String),

    /// Failed to open (load) a QLever index.
    Open(String),

    /// A SPARQL SELECT/ASK/CONSTRUCT/DESCRIBE query failed.
    Query(String),

    /// A SPARQL 1.1 Update operation failed.
    Update(String),

    /// A string argument contained an interior NUL byte, which is not allowed
    /// in C strings.
    NulByte,

    /// The C library returned a string that is not valid UTF-8.
    Utf8,
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::IndexBuild(msg) => write!(f, "QLever index build failed: {msg}"),
            Error::Open(msg) => write!(f, "QLever failed to open index: {msg}"),
            Error::Query(msg) => write!(f, "QLever SPARQL query failed: {msg}"),
            Error::Update(msg) => write!(f, "QLever SPARQL update failed: {msg}"),
            Error::NulByte => write!(f, "argument contains an interior NUL byte"),
            Error::Utf8 => write!(
                f,
                "QLever returned a string that is not valid UTF-8"
            ),
        }
    }
}

impl std::error::Error for Error {}

/// Convenience alias used throughout the `qlever` crate.
pub type Result<T> = std::result::Result<T, Error>;
