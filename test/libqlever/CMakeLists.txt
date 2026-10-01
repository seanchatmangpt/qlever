addLinkAndDiscoverTestNoLibs(QleverTest qlever)

# The C FFI test executable is built in src/libqlever. Register it with CTest
# here so the repository's normal test court executes it instead of merely
# compiling it.
add_test(NAME QleverCTests COMMAND $<TARGET_FILE:qlever_c_tests>)
set_tests_properties(QleverCTests PROPERTIES LABELS "QleverCTests")
