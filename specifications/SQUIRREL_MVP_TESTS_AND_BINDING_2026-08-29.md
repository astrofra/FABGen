# Squirrel MVP Tests And Binding Progress

Date: Saturday, August 29, 2026

## Scope

This work focused on two concrete steps inside FABGen, without expanding into Harfang engine integration:

1. Add focused unit tests that validate the existing Lua binding on the required interoperability surface.
2. Start a functional Squirrel backend and validate it with the same kind of tests.

The target behaviors were:

- Execute a Lua or Squirrel script.
- Exchange integers, floats, strings, arrays, and tables between script and C++.
- Call C++ functions from script.
- Call script functions back from C++.

## What Was Added

### New Squirrel Backend

New files:

- `lang/squirrel.py`
- `lib/squirrel/__init__.py`
- `lib/squirrel/std.py`
- `lib/squirrel/stl.py`

Implemented MVP support:

- Squirrel generator wiring in `bind.py` through `--squirrel`.
- Primitive conversions for `bool`, integer types, `float`, `double`, `const char *`, and `std::string`.
- Embedded module creation and binding helpers for Squirrel.
- Reverse callback support for `std::function<>` closures captured from Squirrel and invoked later from C++.
- `std::vector<T>` exchange through Squirrel arrays.
- `std::map<std::string, int>` exchange through Squirrel tables.

Current explicit limitation:

- Class binding is not implemented yet in the Squirrel backend. The current MVP is intentionally function-centric.

### Test Runner Changes

Updated files:

- `tests.py`
- `gen.py`

Key changes:

- Added a Squirrel test bed that builds a small embedded host executable, binds `my_test` into a Squirrel VM, and runs `test.nut`.
- Added `--sqbase` to point at an official Squirrel source tree.
- Added skip handling before generation so Squirrel only runs tests that explicitly define `test_squirrel`.
- Updated Windows CMake generation to use `Visual Studio 17 2022` with an explicit architecture.
- Made Lua SDK/runtime path resolution less rigid so existing Harfang Lua builds can be reused.
- Fixed generated headers to include `fabgen.h`, which is required for `OwnershipPolicy`.

### Test Coverage Added

Updated tests:

- `tests/basic_type_exchange.py`
- `tests/std_function.py`

New test:

- `tests/script_collection_exchange.py`

Covered scenarios:

- `basic_type_exchange`
  - Script execution.
  - Integer, float, and string exchange.
  - Script-to-C++ function calls.
- `script_collection_exchange`
  - Array exchange through `std::vector<int>`.
  - Table exchange through `std::map<std::string, int>`.
- `std_function`
  - C++ storing and invoking script callbacks.
  - Reverse call path from C++ into Lua/Squirrel.

## Validation Performed

### Squirrel

Validated on Saturday, August 29, 2026 against the official Squirrel source tree cloned under:

- `%TEMP%\fabgen_squirrel_ref2`

Command executed:

```powershell
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2"
```

Observed result:

- `3` tests run
- `0` failures
- `27` skipped intentionally

Passing Squirrel tests:

- `basic_type_exchange`
- `script_collection_exchange`
- `std_function`

### Lua

Validated on Saturday, August 29, 2026 against a local Harfang Lua build produced on July 8, 2025 and located under:

- `S:\hg\harfang3d\build\extern\lua`

Commands executed:

```powershell
python tests.py --luabase "S:\hg\harfang3d\build\extern\lua" --x64 --debug basic_type_exchange
python tests.py --luabase "S:\hg\harfang3d\build\extern\lua" --x64 --debug script_collection_exchange
python tests.py --luabase "S:\hg\harfang3d\build\extern\lua" --x64 --debug std_function
```

Observed result:

- `basic_type_exchange`: passed
- `script_collection_exchange`: passed
- `std_function`: passed

Important note:

- The local Lua build is `x64`. Running the FABGen Lua tests without `--x64` produced an architecture mismatch and failed linkage, so the successful validation was done with `--x64`.

## Practical State After This Change

Step 1 is in place for the requested interoperability surface.

- Lua is validated on the requested script/function/value exchange subset.
- Squirrel now has a functional embedded MVP for the same subset.

Step 2 is started but intentionally not complete.

- Squirrel function-level binding works.
- Primitive, string, array, table, and callback exchange works for the tested cases.
- Broader parity with Lua, especially class binding and the larger historical FABGen matrix, still remains to be implemented.

## Recommended Next Work

- Implement Squirrel class binding support in `lang/squirrel.py`.
- Extend `test_squirrel` coverage to existing tests such as `function_call`, `std_vector`, and structure-oriented cases once class support exists.
- Add non-embedded/public packaging decisions for Squirrel beyond the current embedded host test path.
