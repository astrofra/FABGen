# QuickJS backend

FABGen generates C++14 bindings for **official QuickJS 2026-06-04**. Select
`--quickjs` in `bind.py`; shared declarations continue to use the ordinary
FABGen API. QuickJS-NG and the removed operator-overloading extensions are not
used. The backend implements the FABGen portion of the
[integration specification](specifications/SPECS_QUICKJS_LANG_INTEGRATION_FEASIBILITY.md).

```sh
python bind.py examples/quickjs/bind_example.py --quickjs --out build/quickjs
```

Output consists of `bind_QuickJS.cpp`, `bind_QuickJS.h`, `fabgen_quickjs.h`, and
`fabgen.h`. Compile the wrapper as C++, the runtime as C, and link **one**
compatible QuickJS runtime into the host. All generated translation units in
that host must use the same `fabgen_quickjs.h`. `--prefix` controls exported C++
symbols; `--out_prefix` prefixes the binding filenames while leaving the shared
support header unprefixed.

## JavaScript contract

| Binding | JavaScript behavior |
| --- | --- |
| Constructors | `new module.Type(...)`; JS subclasses honor `new.target.prototype` |
| Members / static members | Accessors on instances / constructors; const members have no setter |
| Arithmetic | `add`, `sub`, `mul`, `div` return the declared native result |
| In-place arithmetic | `addAssign`, `subAssign`, `mulAssign`, `divAssign` mutate and return `this` |
| Comparisons | `equals`, `notEquals`, `lessThan`, `lessEqual`, `greaterThan`, `greaterEqual`, where declared |
| Default equality | `.equals()` compares native pointers, or pointees for shared-pointer proxies; `===` compares JS identity |
| Integer inputs | Finite, integral, in-range Numbers; 64-bit types additionally accept checked BigInts |
| Integer outputs | Native integers of at least 64 bits always produce BigInt; smaller integers produce Number |
| Floating inputs | Number only, without object/string coercion |
| Strings | UTF-8; `std::string` preserves embedded NUL; C strings reject embedded NUL |
| No logical result | `undefined` |
| One logical result | That value, including a returned collection |
| Multiple logical results | Array: primary result first, followed by outputs in native argument order |
| In/out native object | The original JS wrapper is returned |
| Wrapped sequences | Zero-based `get(index)`, `set(index, value)`, and read-only Number `length` |
| Array to vector | Copy conversion; ordinary dense arrays only; reject holes, accessors, proxies and invalid elements |
| Object to map | Own enumerable string data properties; result has a null prototype |
| Native exceptions | Caught at every generated JS callback boundary and reported as JS errors |

An integral Number must also be within `Number.MAX_SAFE_INTEGER`, including for
64-bit inputs. Values outside signed/unsigned 64-bit bounds are rejected before
conversion; `JS_ToBigInt64` is not used as an overflow check. `long`, `size_t`,
and pointer-sized integers follow their actual native width. Harfang's
`int64_t`-based nanosecond times therefore stay exact. Number/BigInt arithmetic
still needs explicit conversion in application code.

Overloads test entire signatures, including native cast compatibility. Integer
candidates precede floating candidates; equal-priority candidates retain
declaration order. A later argument mismatch permits another overload to match.
Defaults apply to omitted arguments, not explicit `undefined`. `null` is accepted
for native object/opaque pointer arguments, not C++ references or scalar values.
Scalar pointer parameters use FABGen's existing scalar conversion rules unless
an explicit pointer converter has been bound. Opaque pointers are borrowed; an
owning pointer requires a class converter that defines destruction.

Named operators that collide with declared members, duplicate exports, unknown
types/features, foreign-language converters, and unsafe callback return types
produce generation errors identifying the declaration. The backend does not
generate JavaScript infix operators or numeric `[]` interception.

Use `lib.quickjs.stl.QuickJSArrayToStdVectorConverter` for array overloads and
`QuickJSObjectToStdMapConverter` for `std::map<std::string, T>`. Arrays/maps convert
into temporary native containers and commit only after successful conversion.
Typed arrays and zero-copy buffer views are not implemented.

## Embedding and modules

For a module named `example` and the default prefix, generated entry points are:

```cpp
// Register before evaluating a JS module importing "example".
gen_js_init_module_example(ctx, "example");

// Alternative: create an owned plain object to inject into an embedded host.
JSValue api = gen_create_example(ctx);
// ... use api ...
JS_FreeValue(ctx, api);

// Disconnect native callbacks, then release every generated module before
// JS_FreeContext / JS_FreeRuntime. Release is idempotent.
gen_release_example(ctx);
```

The ES module exports declarations by name and a default live module object.
ES namespace properties cannot themselves be native accessors. Mutable globals
therefore have `get_name()` / `set_name(value)` exports and a live accessor on the
default object; their direct named export is an initialization snapshot. Const
globals are ordinary exports. This preserves standard ES-module semantics.

`--embedded` retains both linked registration and object creation but omits the
optional dynamic-loader alias. For a public binding,
`FABGEN_QUICKJS_DYNAMIC_MODULE` additionally exports `js_init_module`.
Windows hosts should use linked registration: the stock upstream loader does
not load native DLL modules there.

`<prefix>_type_info`, `get_bound_type_info`, `get_c_type_info`, and
`link_binding` provide the native conversion/linker interface. Native type tags
derive from C++ type names, independently of symbol prefixes or JS aliases.
Public/embedded copies share the inline support registry across linked
translation units, with prototypes per context and native class registration
per runtime. Separate DLLs need a host-owned shared registry implementation;
do not assume C++ inline statics are shared across DLL boundaries.

## Ownership and callbacks

Constructors allocate owned native objects. Value results copy, moveable
noncopyable results move, and reference results borrow. Finalizers never delete
borrowed objects. Borrowed results conservatively retain their receiver and
object arguments; the native class marks these edges for QuickJS cycle
collection. Shared-pointer proxy features, native inheritance/casts, and
noncopyable types use the normal FABGen declarations. JavaScript's prototype
chain follows the first native base; generated methods and native casts cover
additional declared bases.

Retaining a parent does **not** prevent C++ from reallocating storage or deleting
an externally owned object. Bindings returning references into mutable vectors,
scene resources, or externally managed objects must use value copies, stable
native handles, or a host-defined invalidation mechanism. FABGen cannot infer
those engine lifetimes. Finalizers are not a substitute for explicit resource
disposal in the portable Harfang API.

`lib.stl.bind_function_T` supports JS functions as `std::function` arguments and
native `std::function` results as callable JS functions. JS callbacks are retained
as explicit context roots and called with `this === undefined`; bind a receiver
in JavaScript when needed. Reverse bindings generated by `rbind_function` accept
an explicit `JSContext *`, callable, receiver, native arguments, and optional
`bool *success`. With a success pointer, failures set it to false and leave the
exception in the context for `JS_GetException`. Without it, a pending-exception
sentinel propagates through C++ to the generated JS boundary. Returned Promises
are rejected for these synchronous callbacks.

On shutdown, disconnect callbacks and release every generated module on the
owning thread. Each module runs its custom free code once; the final release
clears retained JS values and invalidates remaining native callback copies.
Calling a retained callback after release or from another thread throws a C++
error before touching QuickJS. Callback destruction while the context is live
must also occur on its owning thread. Unregister callbacks to break application
cycles during normal execution; arbitrary C++ `std::function` captures are not
visible to QuickJS's collector. Do not concurrently access a runtime or race
shutdown with worker threads.

Reverse arguments that borrow native storage retain the native caller's lifetime
requirements. Noncopyable, return-by-reference/pointer, and temporary-storage callback results
are rejected because the result would outlive the JS conversion storage.
Separate runtimes must exchange primitives or explicitly rewrapped native data,
never raw `JSValue` handles or closures.

## Build and validation

Download the [official archive](https://bellard.org/quickjs/quickjs-2026-06-04.tar.xz)
and extract it outside generated output. The inspected archive SHA-256 is
`b376e839b322978313d929fd20663b11ba58b75df5a46c126dd19ea2fa70ad2a`.
No runtime download or installation occurs when generating bindings.

`cmake/QuickJS.cmake` builds the core with upstream's source list and required
flags, excluding the optional `quickjs-libc` OS services. It pins the version,
stages `quickjs.h` separately to avoid `VERSION` shadowing C++ `<version>` on
Windows, and includes standard `stddef.h` before upstream's fallback `offsetof`.
It requires a GNU-compatible C compiler. MSVC/clang-cl integration is an explicit
unverified gate, not an interchangeable C++ ABI assumption.

```sh
cmake -S examples/quickjs -B build/quickjs-example -G Ninja \
  -DFABGEN_QUICKJS_SOURCE_DIR=/path/to/quickjs-2026-06-04
cmake --build build/quickjs-example
ctest --test-dir build/quickjs-example --output-on-failure

python tests.py --qjsbase /path/to/quickjs-2026-06-04
python tests.py --qjsbase /path/to/quickjs-2026-06-04 --qjs-debug
python -m unittest test_quickjs_generator
```

Set `CC`/`CXX` to compiler executable paths, or pass `--qjs-cc` / `--qjs-cxx`.
`--qjs-cc /path/to/zig` uses Zig's `cc` and `c++` drivers, including on Windows.
`--tests quickjs_contract quickjs_registry` selects tests and `--keep-failed`
preserves failure artifacts. The test runtime builds once per suite. The host
uses bounded jobs, interruption, memory limits, repeated contexts/runtimes, and
orderly release; it does not depend on a system `qjs` executable.

Validation covers all existing FABGen test families plus exact integer bounds,
conversion failures, parent/cycle lifetimes, callback teardown/thread checks,
explicit reverse receivers, and public/embedded registry sharing. Local runtime
validation uses Windows x64, official QuickJS, and Zig 0.14.1's Clang/GNU ABI.
Linux execution and integration with Harfang's MSVC engine are separate gates.

## Harfang and the hybrid web plan

The unchanged `harfang3d/binding/bind_harfang.py` can generate an embedded
QuickJS wrapper, and the generated C++ compiles against the local Harfang
headers with the Windows GNU-compatible compiler. This checks the declarations
that script currently emits; it is not a linked or rendered Harfang application.
Its QuickJS-specific vector constructor/array-overload branches, engine value
bridges, startup/shutdown hooks, and scene-VM declarations still need to be added
in the Harfang repository. Successful generation does not fill those missing
language branches automatically.

The named math methods, exact nanoseconds, value-copy behavior, multiple-output
arrays, and configurable native module name follow the
[hybrid specification](../harfang3d/specifications/SPECS_HYBRID_CPP_JS_WEBGL_FEASIBILITY.md).
An eventual launcher can register generated exports as `harfang-native` and put
the portable `harfang` JS facade above them. This backend does not implement
`SceneQuickJSVM`, engine capability classification, browser/WebGL code, async
resource loading, the scene factory contract, asset imports, or bytecode caching.
Those remain host/engine work. Production hosts must supply their own compiled
asset module loader, promise rejection reporting, and frame/job scheduling.
