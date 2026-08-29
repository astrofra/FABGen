# Squirrel Class Binding Phase 2

Date: Saturday, August 29, 2026

## Scope

This phase extended the initial Squirrel MVP with a first functional class binding layer, still keeping the work focused on FABGen itself rather than Harfang integration.

The immediate goal was practical:

- make Squirrel classes usable in generated bindings,
- validate them with the same style of unit tests already used for Lua,
- keep the implementation small enough to iterate safely.

## What Was Implemented

Updated file:

- `lang/squirrel.py`

The Squirrel backend now supports a first working class model based on native Squirrel classes and instances:

- Class registration in generated Squirrel modules.
- Per-instance FABGen wrapper storage through `sq_setclassudsize()`.
- Type tagging through `sq_settypetag()`.
- Ownership cleanup through a generated Squirrel release hook.
- Script-side constructors for bound classes.
- Instance member reads and writes through `_get` and `_set`.
- Instance methods and static methods registered as native class slots.
- C++ to Squirrel object conversion through `sq_createinstance()`.
- Squirrel to C++ object conversion with FABGen type-tag cast checks.

## Constructor Model

Squirrel does not use the same constructor model as Lua.

Lua FABGen constructors are factory-style proxies that create and return a wrapped object.
Squirrel constructors are invoked on an already-created class instance.

The phase 2 implementation handles this by:

1. letting Squirrel allocate the class instance,
2. reusing the generated FABGen constructor proxy internally,
3. transferring the produced wrapped C++ object into the Squirrel-created instance storage,
4. attaching the release hook to the final instance.

This kept the implementation compatible with FABGen's existing constructor proxy generation without rewriting the full overload dispatch logic.

## Unit Tests Added

Updated tests:

- `tests/struct_instantiation.py`
- `tests/struct_member_access.py`
- `tests/struct_method_call.py`
- `tests/struct_exchange.py`

New Squirrel coverage now validates:

- Constructing bound classes from Squirrel.
- Reading and writing bound C++ struct members from Squirrel.
- Calling bound instance methods and static methods from Squirrel.
- Passing wrapped objects between Squirrel and C++ by value, pointer, and reference.
- Returning wrapped objects from C++ back to Squirrel.

## Validation Results

Validated on Saturday, August 29, 2026 against the official Squirrel source tree located at:

`C:\Users\fra\AppData\Local\Temp\fabgen_squirrel_ref2`

Targeted class test commands:

```powershell
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug struct_instantiation
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug struct_member_access
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug struct_method_call
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug struct_exchange
```

Result:

- `4 run, 0 failed`

Full currently-enabled Squirrel suite:

```powershell
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2"
```

Result on Saturday, August 29, 2026:

- `7 run, 0 failed, 23 skipped`

Passing Squirrel tests:

- `basic_type_exchange`
- `script_collection_exchange`
- `std_function`
- `struct_exchange`
- `struct_instantiation`
- `struct_member_access`
- `struct_method_call`

## Current Limits

This is an intentionally small phase 2 slice, not full Lua parity yet.

Known limits after this step:

- Static data members are not exposed yet as Squirrel property-style fields.
- Sequence-style class behavior is not implemented yet for Squirrel classes.
- Arithmetic and comparison metamethod binding for Squirrel classes is not implemented yet.
- The class `from_c` path currently assumes the generated module has been bound into the Squirrel root table.
- Broader historical FABGen tests still need `test_squirrel` coverage before they can validate the class backend more deeply.

## Practical Outcome

The Squirrel backend is no longer function-only.

At this point it can validate the core object workflow required for the first integration steps:

- execute a Squirrel script,
- exchange primitive values, arrays, and tables,
- call C++ from Squirrel,
- call Squirrel callbacks from C++,
- create and use wrapped C++ class instances from Squirrel.

## Recommended Next Steps

- Add Squirrel tests for `function_call` and `std_vector`.
- Extend the class backend to support static data members.
- Add Squirrel support for sequence features on wrapped classes.
- Add inheritance-specific Squirrel tests once class inheritance behavior is intentionally designed.
