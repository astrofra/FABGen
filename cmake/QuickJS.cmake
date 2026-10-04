# Official QuickJS core for linked native modules (not quickjs-libc).
# Caller sets FABGEN_QUICKJS_SOURCE_DIR to an extracted 2026-06-04 archive.
if(TARGET fabgen_quickjs)
    return()
endif()
file(TO_CMAKE_PATH "${FABGEN_QUICKJS_SOURCE_DIR}" FABGEN_QUICKJS_SOURCE_DIR)
if(NOT EXISTS "${FABGEN_QUICKJS_SOURCE_DIR}/VERSION")
    message(FATAL_ERROR "Set FABGEN_QUICKJS_SOURCE_DIR to official QuickJS 2026-06-04")
endif()
file(STRINGS "${FABGEN_QUICKJS_SOURCE_DIR}/VERSION" _fabgen_qjs_version LIMIT_COUNT 1)
if(NOT _fabgen_qjs_version STREQUAL "2026-06-04")
    message(FATAL_ERROR "FABGen QuickJS requires reviewed version 2026-06-04, found ${_fabgen_qjs_version}")
endif()
if(MSVC)
    message(FATAL_ERROR "Official QuickJS needs a GNU-compatible C toolchain. Use MinGW/Clang GNU mode; MSVC integration requires a separate verified runtime build.")
endif()

# Do not export upstream's directory: VERSION shadows C++ <version> on Windows.
set(_fabgen_qjs_include "${CMAKE_CURRENT_BINARY_DIR}/fabgen_quickjs_include")
file(MAKE_DIRECTORY "${_fabgen_qjs_include}")
configure_file("${FABGEN_QUICKJS_SOURCE_DIR}/quickjs.h" "${_fabgen_qjs_include}/quickjs.h" COPYONLY)
add_library(fabgen_quickjs STATIC
    "${FABGEN_QUICKJS_SOURCE_DIR}/quickjs.c"
    "${FABGEN_QUICKJS_SOURCE_DIR}/dtoa.c"
    "${FABGEN_QUICKJS_SOURCE_DIR}/libregexp.c"
    "${FABGEN_QUICKJS_SOURCE_DIR}/libunicode.c"
    "${FABGEN_QUICKJS_SOURCE_DIR}/cutils.c")
set_target_properties(fabgen_quickjs PROPERTIES C_STANDARD 11 C_EXTENSIONS ON POSITION_INDEPENDENT_CODE ON)
# Supply the standard offsetof before cutils.h's null-pointer fallback macro.
# This also permits unoptimized Clang/Zig UBSan builds without false traps.
target_compile_options(fabgen_quickjs PRIVATE -fwrapv -include stddef.h)
target_compile_definitions(fabgen_quickjs PRIVATE _GNU_SOURCE CONFIG_VERSION="2026-06-04")
target_include_directories(fabgen_quickjs PUBLIC "${_fabgen_qjs_include}")
find_package(Threads REQUIRED)
target_link_libraries(fabgen_quickjs PUBLIC Threads::Threads)
if(WIN32)
    target_compile_definitions(fabgen_quickjs PRIVATE __USE_MINGW_ANSI_STDIO)
else()
    target_link_libraries(fabgen_quickjs PUBLIC m ${CMAKE_DL_LIBS})
endif()
