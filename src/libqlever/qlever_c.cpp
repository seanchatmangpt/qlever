// Copyright 2025 The QLever Authors, in particular:
//
// 2025 Johannes Kalmbach <kalmbach@cs.uni-freiburg.de>, UFR
//
// UFR = University of Freiburg, Chair of Algorithms and Data Structures

// C shim implementation for the QLever embedded C++ API.
//
// All C++ exceptions are caught at the FFI boundary and stored in a
// thread-local string; callers retrieve them with `qlever_last_error()`.

#include "libqlever/qlever_c.h"

#include <cstdlib>
#include <cstring>
#include <string>

#include "libqlever/Qlever.h"
#include "util/MemorySize/MemorySize.h"

// ---------------------------------------------------------------------------
// Thread-local error storage
// ---------------------------------------------------------------------------
namespace {
thread_local std::string tl_last_error;

void set_error(const char* msg) { tl_last_error = msg ? msg : "unknown error"; }

// Copy a std::string into a malloc'd buffer so the caller can free it.
char* copy_to_heap(const std::string& s) {
  char* buf = static_cast<char*>(std::malloc(s.size() + 1));
  if (buf) {
    std::memcpy(buf, s.data(), s.size());
    buf[s.size()] = '\0';
  }
  return buf;
}

// Convert a memory-limit value in GB to an optional MemorySize.
// A value <= 0 means "use the default" (1 GB, same as the C++ default).
std::optional<ad_utility::MemorySize> to_memory_size(double gb) {
  if (gb <= 0.0) return std::nullopt;
  return ad_utility::MemorySize::bytes(
      static_cast<uint64_t>(gb * 1024.0 * 1024.0 * 1024.0));
}
}  // namespace

// ---------------------------------------------------------------------------
// Opaque handle definition
// ---------------------------------------------------------------------------
struct QleverHandle {
  qlever::Qlever engine;
  explicit QleverHandle(const qlever::EngineConfig& cfg) : engine(cfg) {}
};

// ---------------------------------------------------------------------------
// Public API implementation
// ---------------------------------------------------------------------------

extern "C" {

// qlever_build_index --------------------------------------------------------
int qlever_build_index(const char* base_name, const char* input_file,
                       double memory_limit_gb) {
  if (!base_name || !input_file) {
    set_error("base_name and input_file must not be NULL");
    return 1;
  }
  try {
    qlever::IndexBuilderConfig cfg;
    cfg.baseName_ = base_name;
    cfg.inputFiles_.push_back(
        {input_file, qlever::Filetype::Turtle, std::nullopt});
    if (auto ms = to_memory_size(memory_limit_gb)) {
      cfg.memoryLimit_ = *ms;
    }
    qlever::Qlever::buildIndex(std::move(cfg));
    return 0;
  } catch (const std::exception& e) {
    set_error(e.what());
    return 1;
  } catch (...) {
    set_error("unknown C++ exception in qlever_build_index");
    return 1;
  }
}

// qlever_create -------------------------------------------------------------
QleverHandle* qlever_create(const char* base_name, double memory_limit_gb,
                            int persist_updates) {
  if (!base_name) {
    set_error("base_name must not be NULL");
    return nullptr;
  }
  try {
    qlever::EngineConfig cfg;
    cfg.baseName_ = base_name;
    if (auto ms = to_memory_size(memory_limit_gb)) {
      cfg.memoryLimit_ = *ms;
    }
    cfg.persistUpdates_ = (persist_updates != 0);
    return new QleverHandle(cfg);
  } catch (const std::exception& e) {
    set_error(e.what());
    return nullptr;
  } catch (...) {
    set_error("unknown C++ exception in qlever_create");
    return nullptr;
  }
}

// qlever_destroy ------------------------------------------------------------
void qlever_destroy(QleverHandle* handle) { delete handle; }

// qlever_query --------------------------------------------------------------
char* qlever_query(const QleverHandle* handle, const char* sparql) {
  if (!handle || !sparql) {
    set_error("handle and sparql must not be NULL");
    return nullptr;
  }
  try {
    std::string result = handle->engine.query(std::string(sparql));
    return copy_to_heap(result);
  } catch (const std::exception& e) {
    set_error(e.what());
    return nullptr;
  } catch (...) {
    set_error("unknown C++ exception in qlever_query");
    return nullptr;
  }
}

// qlever_update -------------------------------------------------------------
char* qlever_update(QleverHandle* handle, const char* sparql_update) {
  if (!handle || !sparql_update) {
    set_error("handle and sparql_update must not be NULL");
    return nullptr;
  }
  try {
    std::string result = handle->engine.update(std::string(sparql_update));
    return copy_to_heap(result);
  } catch (const std::exception& e) {
    set_error(e.what());
    return nullptr;
  } catch (...) {
    set_error("unknown C++ exception in qlever_update");
    return nullptr;
  }
}

// qlever_free_string --------------------------------------------------------
void qlever_free_string(char* str) { std::free(str); }

// qlever_last_error ---------------------------------------------------------
const char* qlever_last_error(void) { return tl_last_error.c_str(); }

// qlever_version ------------------------------------------------------------
const char* qlever_version(void) {
  // Defined in CompilationInfo.cmake / generated header when available.
  // Fall back to a hard-coded string that matches the latest release tag.
  return "0.5.45";
}

}  // extern "C"
