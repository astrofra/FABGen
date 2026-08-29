# Squirrel Class Binding Phase 2

Date: Saturday, August 29, 2026

Update on Sunday, August 30, 2026:
Inheritance-focused and extern-type Squirrel tests were added and validated. The full Squirrel suite now stands at `29 run, 0 failed, 1 skipped`.

## Scope

This phase extended the initial Squirrel MVP with a first functional class binding layer, still keeping the work focused on FABGen itself rather than Harfang integration.

The immediate goal was practical:

- make Squirrel classes usable in generated bindings,
- validate them with the same style of unit tests already used for Lua,
- keep the implementation small enough to iterate safely.

## What Was Implemented

Updated files:

- `lang/squirrel.py`
- `gen.py`
- `lib/squirrel/stl.py`
- `tests/arg_out.py`
- `tests/extern_type.py`
- `tests/shared_ptr.py`
- `tests/shared_ptr_default_comparison.py`
- `tests/enumeration.py`
- `tests/repr.py`

The Squirrel backend now supports a first working class model based on native Squirrel classes and instances:

- Class registration in generated Squirrel modules.
- Per-instance FABGen wrapper storage through `sq_setclassudsize()`.
- Type tagging through `sq_settypetag()`.
- Ownership cleanup through a generated Squirrel release hook.
- Script-side constructors for bound classes.
- Instance member reads and writes through `_get` and `_set`.
- Instance methods and static methods registered as native class slots.
- Static data members exposed through generated explicit accessors named `get_<member>()` and `set_<member>(value)` on the Squirrel class object.
- Reuse of the same Squirrel proxy for repeated non-owning returns of the same C++ object.
- Arithmetic metamethod binding for `_add`, `_sub`, `_mul`, and `_div`.
- Comparison support through `_cmp` for class-to-class comparisons.
- Default deep comparison through `_cmp` for bound types flagged with FABGen `_supports_deep_compare`, such as `std::shared_ptr<T>` proxy wrappers.
- Class `repr` support through the Squirrel `_tostring` metamethod.
- Sequence-aware classes now expose an explicit `len()` method and a generated `_nexti` metamethod for `foreach` iteration.
- Safe tracked-VM shutdown through a generated `gen_release_<module>(v)` helper called before `sq_close(v)`, which avoids dangling callback releases during process teardown.
- C++ to Squirrel object conversion through `sq_createinstance()`.
- Squirrel to C++ object conversion with FABGen type-tag cast checks.
- Sequence-style `_get` and `_set` support for wrapped classes with the FABGen `sequence` feature.
- FABGen multi-result returns now map to a packed Squirrel array whenever more than one script-visible value must be returned.

The supporting generator layer also received one correctness fix:

- `bind_variable()` now qualifies generated C++ variable access with `::` so global variables do not collide with the Squirrel VM parameter name `v` in generated proxies.

The Squirrel STL layer also received one correctness fix:

- `SquirrelArrayToStdVectorConverter` now uses `std::vector<T>` as its generated C++ storage type, which makes constructor overloads taking Squirrel arrays compile correctly.

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

- `tests/arg_out.py`
- `tests/cpp_exceptions.py`
- `tests/enumeration.py`
- `tests/extern_type.py`
- `tests/function_template_call.py`
- `tests/method_route_feature.py`
- `tests/repr.py`
- `tests/struct_inheritance.py`
- `tests/struct_inheritance_cast.py`
- `tests/function_call.py`
- `tests/return_nullptr_as_none.py`
- `tests/shared_ptr.py`
- `tests/shared_ptr_default_comparison.py`
- `tests/std_vector.py`
- `tests/struct_default_comparison.py`
- `tests/struct_instantiation.py`
- `tests/struct_member_access.py`
- `tests/struct_method_call.py`
- `tests/struct_operator_call.py`
- `tests/struct_static_const_member_access.py`
- `tests/struct_exchange.py`
- `tests/template_struct_nesting.py`
- `tests/transform_rval.py`
- `tests/variable_access.py`
- `tests/struct_bitfield_member_access.py`
- `tests/struct_nesting.py`

New Squirrel coverage now validates:

- Global C++ function calls from Squirrel, including overload resolution and optional arguments.
- `arg_out` and `arg_in_out` behavior from Squirrel.
- Native C++ exception translation into Squirrel runtime errors.
- Null pointer returns mapped to Squirrel `null`.
- `std::shared_ptr<T>` construction, member access through proxy wrappers, and empty `shared_ptr` mapped to Squirrel `null`.
- `std::vector<int>` construction from a Squirrel array.
- Integer-index reads and writes on wrapped sequence-like objects.
- Explicit `len()` calls on wrapped sequence-like objects.
- `foreach` iteration on wrapped sequence-like objects through `_nexti`.
- Implicit cast from a wrapped `std::vector<int>` object to `int *` through FABGen cast rules.
- Constructing bound classes from Squirrel.
- Reading and writing bound C++ struct members from Squirrel.
- Calling bound instance methods and static methods from Squirrel.
- Calling bound methods using the FABGen `route` feature.
- Accessing bound static data members from Squirrel through explicit generated accessors.
- Passing wrapped objects between Squirrel and C++ by value, pointer, and reference.
- Returning wrapped objects from C++ back to Squirrel.
- Preserving Squirrel object identity when the same non-owning C++ object is returned repeatedly.
- Comparing distinct wrapped `std::shared_ptr<T>` handles that refer to the same underlying pointee through default Squirrel `<=>` support.
- Using class arithmetic metamethods (`_add`, `_sub`, `_mul`, `_div`) on bound objects.
- Using class comparison support through `_cmp`, including equality-style checks with `<=>`.
- Passing derived wrapped objects to APIs typed as base-class references or pointers.
- Reusing inherited methods and inherited members on derived Squirrel bindings.
- Preserving virtual dispatch when a derived instance is passed through a base-class API.
- Using generated downcast helper functions such as `Cast_base_class_To_derived_class(...)`.
- Accessing module-level bound variables from Squirrel.
- Accessing named enumeration values from Squirrel.
- Generating and loading modules that declare external FABGen-linked types on the Squirrel side.
- Accessing and mutating bitfield-backed members from Squirrel.
- Accessing nested bound objects through wrapped member references.
- Accessing nested template-instantiated structs from Squirrel.
- Calling explicitly bound C++ function template instantiations from Squirrel.
- Applying `rval_transform` to return derived wrapped objects from a base-pointer API.
- String conversion of wrapped class instances through `_tostring`, `tostring()`, and string concatenation.

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

Additional Squirrel return/enumeration/repr test commands validated later on Saturday, August 29, 2026:

```powershell
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug arg_out
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug enumeration
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug repr
```

Result:

- `3 run, 0 failed`

Additional Squirrel exception/template/route/transform test commands validated later on Saturday, August 29, 2026:

```powershell
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug cpp_exceptions
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug function_template_call
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug method_route_feature
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug template_struct_nesting
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug transform_rval
```

Result:

- `5 run, 0 failed`

Additional Squirrel shared pointer test commands validated later on Saturday, August 29, 2026:

```powershell
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug shared_ptr
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug shared_ptr_default_comparison
```

Result:

- `2 run, 0 failed`

Additional Squirrel inheritance test commands validated on Sunday, August 30, 2026:

```powershell
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug struct_inheritance
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug struct_inheritance_cast
```

Result:

- `2 run, 0 failed`

Additional Squirrel extern-type test command validated on Sunday, August 30, 2026:

```powershell
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug extern_type
```

Result:

- `1 run, 0 failed`

Additional object-port test commands validated later on Saturday, August 29, 2026:

```powershell
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug variable_access
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug struct_bitfield_member_access
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug struct_nesting
```

Result:

- `3 run, 0 failed`

Additional Squirrel function and sequence test commands validated later on Saturday, August 29, 2026:

```powershell
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug function_call
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug std_vector
```

Result:

- `2 run, 0 failed`

The `std_vector` Squirrel test was later extended and revalidated on Saturday, August 29, 2026 to cover:

- `len()` on wrapped `std::vector` instances,
- `foreach` iteration over wrapped `std::vector` instances through `_nexti`.

Additional Squirrel class feature test commands validated later on Saturday, August 29, 2026:

```powershell
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug return_nullptr_as_none
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug struct_static_const_member_access
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug struct_default_comparison
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2" --debug struct_operator_call
```

Result:

- `4 run, 0 failed`

Full currently-enabled Squirrel suite:

```powershell
python tests.py --sqbase "$env:TEMP\fabgen_squirrel_ref2"
```

Result on Sunday, August 30, 2026:

- `29 run, 0 failed, 1 skipped`

Passing Squirrel tests:

- `arg_out`
- `basic_type_exchange`
- `cpp_exceptions`
- `enumeration`
- `extern_type`
- `function_call`
- `function_template_call`
- `method_route_feature`
- `repr`
- `return_nullptr_as_none`
- `script_collection_exchange`
- `shared_ptr`
- `shared_ptr_default_comparison`
- `std_function`
- `std_vector`
- `struct_bitfield_member_access`
- `struct_default_comparison`
- `struct_exchange`
- `struct_inheritance`
- `struct_inheritance_cast`
- `struct_instantiation`
- `struct_member_access`
- `struct_method_call`
- `struct_nesting`
- `struct_operator_call`
- `struct_static_const_member_access`
- `template_struct_nesting`
- `transform_rval`
- `variable_access`

## Current Limits

This is an intentionally small phase 2 slice, not full Lua parity yet.

Known limits after this step:

- Direct class-side property writes such as `MyType.value = ...` are still blocked by the Squirrel VM object model. Mutable static data members are exposed through `MyType.get_value()` / `MyType.set_value(v)` instead.
- Squirrel native closures can only return zero or one VM value. FABGen therefore exposes multi-result bindings as a packed Squirrel array rather than emulating Lua-style multiple returns.
- Sequence support still does not try to emulate every built-in container behavior. It now covers integer `_get/_set`, explicit `len()`, and `foreach` through `_nexti`, but richer parity with native Squirrel containers is still incomplete.
- Squirrel `==` and `!=` on distinct class instances remain identity-based in the VM itself. FABGen now preserves identity for repeated non-owning returns, but value-based equality on separate wrapped instances must currently use `<=>` through `_cmp`. Mixed comparisons such as `instance <=> 4` are still blocked by the VM dispatch rules and do not reach `_cmp`.
- The class `from_c` path currently assumes the generated module has been bound into the Squirrel root table.
- Broader historical FABGen tests still need `test_squirrel` coverage before they can validate the class backend more deeply.

The remaining skipped tests at this point are:

- `std_future`

## Static Data Member Policy

For stock Squirrel, direct property-style mutation on class objects is not a robust target for FABGen-generated static data members.

The backend therefore uses an explicit API for static data:

- `MyType.get_value()` for reads.
- `MyType.set_value(v)` for writes when the C++ static member is mutable.

This keeps the binding consistent with the actual Squirrel VM behavior:

- no stale registration-time snapshot,
- no fake property semantics that diverge after mutation,
- no dependence on a patched Squirrel runtime.

## VM Shutdown Policy

Squirrel callbacks captured into C++ `std::function` objects may outlive the point where the host decides to close the VM.

To make that shutdown path reliable, the generated Squirrel backend now exposes a release helper:

- `gen_release_<module>(v)`

The embedding host should call this helper before `sq_close(v)`.
The helper releases tracked instance-cache references and marks tracked callback references as no longer safe to release through the VM.

The FABGen Squirrel test host was updated accordingly, and the previously intermittent `std_function` Squirrel test was revalidated after that change.

## Multi-Result Return Policy

Stock Squirrel native closures do not support Lua-style multiple return values.

To keep `arg_out` and `arg_in_out` usable without forking the VM, the backend now uses this rule:

- If the binding exposes exactly one script-visible result, that value is returned directly.
- If the binding exposes more than one script-visible result, FABGen packs them into a Squirrel array in the same order as the existing FABGen result list.

Examples:

- `void f(int &a, int *b)` with `arg_out: [a, b]` returns `[a, b]`.
- `bool g(int *v)` with `arg_in_out: [v]` returns `[result, v]`.
- `void h(MyType *obj)` with only one object `arg_in_out` still returns the object directly.

## Shared Pointer Comparison Policy

For stock Squirrel, `==` and `!=` on class instances remain VM identity checks and do not consult FABGen comparison logic.

For `std::shared_ptr<T>` proxy wrappers and any other bound type that enables FABGen `_supports_deep_compare`, the Squirrel backend now generates a default `_cmp` metamethod when no explicit comparison operators are bound.

This gives a practical rule:

- repeated non-owning returns of the same wrapped C++ object keep `==` working through instance identity reuse,
- distinct wrappers that still represent equal deep values, such as aliased `std::shared_ptr<T>` handles, should be compared from Squirrel with `<=>`.

## Practical Outcome

The Squirrel backend is no longer function-only.

At this point it can validate the core object workflow required for the first integration steps:

- execute a Squirrel script,
- exchange primitive values, arrays, and tables,
- exchange named enum values,
- call C++ from Squirrel,
- call Squirrel callbacks from C++,
- propagate native C++ exceptions into Squirrel failures,
- use `arg_out` / `arg_in_out` within the VM's single-return model,
- call bound function-template instantiations,
- exercise routed method bindings,
- create and use wrapped C++ class instances from Squirrel,
- use base/derived class relationships through FABGen cast rules and inherited bindings,
- use proxied `std::shared_ptr<T>` wrappers, including null returns and deep comparison through `<=>`,
- expose derived wrapped instances through `rval_transform`,
- stringify wrapped class instances through `_tostring`,
- iterate wrapped sequence-like classes from Squirrel with `foreach`.

## Recommended Next Steps

- Keep the explicit static accessor policy unless a custom Squirrel runtime is accepted.
- Add richer sequence parity beyond `len()` and `foreach`, only where the Squirrel VM model makes it worthwhile.
- Add inheritance-specific Squirrel tests once class inheritance behavior is intentionally designed.
