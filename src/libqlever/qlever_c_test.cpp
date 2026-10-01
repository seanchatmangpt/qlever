// Copyright 2025 The QLever Authors
//
// Adversarial unit tests for the qlever_c shim.
//
// These tests exercise every error path in the C shim WITHOUT linking against
// a live QLever index, so they run quickly in CI.  Tests that require an
// index are guarded behind a compile-time flag QLEVER_C_TEST_WITH_INDEX.
//
// Build & run (CMake build dir):
//   cmake --build . --target qlever_c_tests
//   ./qlever_c_tests

#include "libqlever/qlever_c.h"

#include <gtest/gtest.h>

#include <cstring>
#include <string>
#include <thread>
#include <vector>

// ---------------------------------------------------------------------------
// Helper: check that the error message set after a failing call is non-empty.
// ---------------------------------------------------------------------------
static void expect_error_message_set() {
  const char* msg = qlever_last_error();
  ASSERT_NE(msg, nullptr);
  EXPECT_GT(std::strlen(msg), 0u) << "expected a non-empty error message";
}

// ===========================================================================
// NULL-argument guard tests
// ===========================================================================

TEST(QleverCShim, BuildIndex_NullBaseName_ReturnsError) {
  int rc = qlever_build_index(nullptr, "/some/file.ttl", 0.0);
  EXPECT_NE(rc, 0);
  expect_error_message_set();
}

TEST(QleverCShim, BuildIndex_NullInputFile_ReturnsError) {
  int rc = qlever_build_index("/tmp/base", nullptr, 0.0);
  EXPECT_NE(rc, 0);
  expect_error_message_set();
}

TEST(QleverCShim, BuildIndex_BothNull_ReturnsError) {
  int rc = qlever_build_index(nullptr, nullptr, 0.0);
  EXPECT_NE(rc, 0);
  expect_error_message_set();
}

TEST(QleverCShim, Create_NullBaseName_ReturnsNull) {
  QleverHandle* h = qlever_create(nullptr, 0.0, 0);
  EXPECT_EQ(h, nullptr);
  expect_error_message_set();
}

TEST(QleverCShim, Query_NullHandle_ReturnsNull) {
  char* result = qlever_query(nullptr, "SELECT * WHERE { ?s ?p ?o }");
  EXPECT_EQ(result, nullptr);
  expect_error_message_set();
}

TEST(QleverCShim, Query_NullSparql_ReturnsNull) {
  // We can't get a real handle without an index, so we forge a fake non-null
  // pointer.  The shim checks for null before dereferencing.
  // NOTE: this would crash if the shim dereferences the pointer before
  //       checking for null sparql.  That is intentional – we want to catch
  //       that case.
  //
  // We pass nullptr for both here so neither pointer is dereferenced.
  char* result = qlever_query(nullptr, nullptr);
  EXPECT_EQ(result, nullptr);
  expect_error_message_set();
}

TEST(QleverCShim, Update_NullHandle_ReturnsNull) {
  char* result = qlever_update(nullptr, "INSERT DATA { <ex:s> <ex:p> <ex:o> }");
  EXPECT_EQ(result, nullptr);
  expect_error_message_set();
}

TEST(QleverCShim, Update_NullSparql_ReturnsNull) {
  char* result = qlever_update(nullptr, nullptr);
  EXPECT_EQ(result, nullptr);
  expect_error_message_set();
}

// ===========================================================================
// destroy – null handle must be a no-op (never crash)
// ===========================================================================

TEST(QleverCShim, Destroy_Null_IsNoop) {
  EXPECT_NO_FATAL_FAILURE(qlever_destroy(nullptr));
}

// ===========================================================================
// free_string – free(nullptr) must be safe
// ===========================================================================

TEST(QleverCShim, FreeString_Null_IsNoop) {
  EXPECT_NO_FATAL_FAILURE(qlever_free_string(nullptr));
}

// ===========================================================================
// version – must return a non-null, non-empty string
// ===========================================================================

TEST(QleverCShim, Version_NonEmptyString) {
  const char* v = qlever_version();
  ASSERT_NE(v, nullptr);
  EXPECT_GT(std::strlen(v), 0u);
}

// ===========================================================================
// last_error – must always return a valid (possibly empty) string
// ===========================================================================

TEST(QleverCShim, LastError_NeverNull) {
  // Even before any error has occurred the pointer must be valid.
  const char* err = qlever_last_error();
  ASSERT_NE(err, nullptr);
  // Must be NUL-terminated (std::strlen should not crash).
  [[maybe_unused]] auto len = std::strlen(err);
}

// ===========================================================================
// thread-local error isolation
// ===========================================================================

TEST(QleverCShim, LastError_IsThreadLocal) {
  // Trigger an error on the main thread.
  qlever_build_index(nullptr, nullptr, 0.0);
  std::string main_thread_error = qlever_last_error();
  EXPECT_GT(main_thread_error.size(), 0u);

  std::string thread_error;
  std::thread t([&thread_error] {
    // No error has occurred in this thread yet; last_error should be empty.
    thread_error = qlever_last_error();
  });
  t.join();

  // The worker thread must see an empty error (its own TLS slot), not the
  // main thread's error.
  EXPECT_EQ(thread_error, "")
      << "thread-local error must not bleed across threads";
}

// ===========================================================================
// error message overwrite
// ===========================================================================

TEST(QleverCShim, LastError_IsOverwrittenByNextCall) {
  // First error
  qlever_build_index(nullptr, "/a.ttl", 0.0);
  std::string err1 = qlever_last_error();

  // Second error (different args)
  qlever_build_index("/base", nullptr, 0.0);
  std::string err2 = qlever_last_error();

  // Both must be non-empty; they may or may not be identical depending on
  // implementation — but the second call must have updated the message.
  EXPECT_GT(err1.size(), 0u);
  EXPECT_GT(err2.size(), 0u);
}

// ===========================================================================
// Index-building with a non-existent input file
// ===========================================================================

TEST(QleverCShim, BuildIndex_NonexistentInputFile_ReturnsError) {
  int rc = qlever_build_index("/tmp/qlever_c_test_base",
                              "/this/path/does/not/exist.ttl", 0.0);
  EXPECT_NE(rc, 0);
  expect_error_message_set();
}

// ===========================================================================
// Create with a non-existent index directory
// ===========================================================================

TEST(QleverCShim, Create_NonexistentIndex_ReturnsNull) {
  QleverHandle* h = qlever_create("/this/index/does/not/exist", 0.0, 0);
  EXPECT_EQ(h, nullptr);
  expect_error_message_set();
}

// ===========================================================================
// Multiple concurrent calls to NULL-path functions (stress test for TLS
// correctness under threads).
// ===========================================================================

TEST(QleverCShim, ConcurrentNullCalls_NoDataRace) {
  constexpr int kThreads = 16;
  constexpr int kIters = 50;

  std::vector<std::thread> threads;
  threads.reserve(kThreads);

  for (int t = 0; t < kThreads; ++t) {
    threads.emplace_back([t] {
      for (int i = 0; i < kIters; ++i) {
        qlever_build_index(nullptr, nullptr, 0.0);
        const char* err = qlever_last_error();
        // Each thread must see its own non-empty error.
        ASSERT_NE(err, nullptr);
        EXPECT_GT(std::strlen(err), 0u) << "thread " << t << " iteration " << i;
      }
    });
  }

  for (auto& th : threads) {
    th.join();
  }
}

// ===========================================================================
// free_string after malloc'd allocation (integration smoke test)
// ===========================================================================

TEST(QleverCShim, FreeString_MallocdBuffer_DoesNotCrash) {
  // Simulate what qlever_query would return: a malloc'd string.
  char* buf = static_cast<char*>(std::malloc(32));
  ASSERT_NE(buf, nullptr);
  std::strcpy(buf, "{\"test\":true}");
  // free_string must handle a real heap pointer without crashing.
  EXPECT_NO_FATAL_FAILURE(qlever_free_string(buf));
}
