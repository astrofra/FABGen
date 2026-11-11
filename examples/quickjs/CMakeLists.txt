cmake_minimum_required(VERSION 3.16)
project(FABGenQuickJSExample LANGUAGES C CXX)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
get_filename_component(FABGEN_ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
include("${FABGEN_ROOT}/cmake/QuickJS.cmake")
set(generated "${CMAKE_CURRENT_BINARY_DIR}/generated")
add_custom_command(
    OUTPUT "${generated}/bind_QuickJS.cpp" "${generated}/bind_QuickJS.h"
           "${generated}/fabgen_quickjs.h" "${generated}/fabgen.h"
    COMMAND "${Python3_EXECUTABLE}" "${FABGEN_ROOT}/bind.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/bind_example.py" --quickjs --out "${generated}"
    DEPENDS bind_example.py "${FABGEN_ROOT}/gen.py" "${FABGEN_ROOT}/bind.py"
            "${FABGEN_ROOT}/lang/quickjs.py" "${FABGEN_ROOT}/lib/quickjs/std.py"
            "${FABGEN_ROOT}/lib/quickjs/stl.py" "${FABGEN_ROOT}/lib/quickjs/runtime.h"
    VERBATIM)
add_executable(fabgen_quickjs_example main.cpp "${generated}/bind_QuickJS.cpp")
target_compile_features(fabgen_quickjs_example PRIVATE cxx_std_14)
target_include_directories(fabgen_quickjs_example PRIVATE "${generated}")
target_link_libraries(fabgen_quickjs_example PRIVATE fabgen_quickjs)
enable_testing()
add_test(NAME example COMMAND fabgen_quickjs_example "${CMAKE_CURRENT_SOURCE_DIR}/main.js")
