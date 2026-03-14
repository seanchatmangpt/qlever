add_library(qlever Qlever.cpp)
qlever_target_link_libraries(qlever parser engine util index absl::strings)

# ---------------------------------------------------------------------------
# qlever_c  –  C-ABI shim that wraps the C++ `qlever` library for FFI use
#              (Rust, Python, Go, …).
#
# We build both a shared library (for dynamic linking / cdylib from Rust) and
# a static library (for staticlib / build-script use with the `cc` crate).
# Both export only the symbols declared in qlever_c.h.
# ---------------------------------------------------------------------------

# Shared library (.so / .dylib / .dll)
add_library(qlever_c SHARED qlever_c.cpp)
qlever_target_link_libraries(qlever_c qlever parser engine util index
                             absl::strings)
set_target_properties(qlever_c PROPERTIES
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN ON
    PUBLIC_HEADER "qlever_c.h"
)

# Static library (.a / .lib)  – useful when embedding into a Rust staticlib
add_library(qlever_c_static STATIC qlever_c.cpp)
qlever_target_link_libraries(qlever_c_static qlever parser engine util index
                             absl::strings)
set_target_properties(qlever_c_static PROPERTIES
    OUTPUT_NAME qlever_c
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN ON
)

# Install rules (used when packaging; optional for embedded use)
install(TARGETS qlever_c qlever_c_static
        LIBRARY DESTINATION lib
        ARCHIVE DESTINATION lib
        PUBLIC_HEADER DESTINATION include/qlever)
