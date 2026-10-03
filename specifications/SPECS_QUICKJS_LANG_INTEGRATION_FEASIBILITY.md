# QuickJS Language Integration Feasibility

Date: 2026-10-03

Scope: integrating JavaScript through Fabrice Bellard's official QuickJS into FABGen and Harfang, with a public language package and an embedded scene VM comparable to Lua. QuickJS is the runtime; JavaScript is the language. QuickJS-NG and Micro QuickJS are separate projects and are not the baseline of this study.

Baseline: QuickJS **2026-06-04**, the latest release listed on the official website when inspected. Local repositories inspected: FABGen `36d9d1c` and Harfang `27edc9b`. This is a source-based feasibility study; no QuickJS backend, executable prototype, or performance benchmark was built for it. Proposed names and code examples below describe a future integration.

## First Question: Does QuickJS Support Operator Overloading?

**Not in current official QuickJS. It did in older releases.** This distinction is decisive for Harfang's vector, matrix, quaternion, and color APIs.

| Version / configuration | User-defined operator overloading | Evidence |
| --- | --- | --- |
| QuickJS 2024-01-13 with the optional bignum extensions enabled | Yes, as a nonstandard extension | `Operators.create`, `Symbol.operatorSet`, `JS_AddIntrinsicOperators`, and `tests/test_op_overloading.js` in the release archive |
| QuickJS 2025-04-26 | Removed with the bignum extensions | Release changelog and absence of the operator implementation/API in the release sources |
| QuickJS 2026-06-04 | No | Current release sources still have no operator extension |
| Standard ECMAScript 2025 | No general user-defined arithmetic operator overloading | Standard operator and primitive-conversion semantics |

The [official changelog](https://bellard.org/quickjs/Changelog) records the removal in the 2025-04-26 release. The official [Bignum Extensions documentation](https://bellard.org/quickjs/jsbignum.html) remains online and describes the historical operator extension; it must not be read as a description of the current runtime. The [2024-01-13](https://bellard.org/quickjs/quickjs-2024-01-13.tar.xz), [2025-04-26](https://bellard.org/quickjs/quickjs-2025-04-26.tar.xz), and [2026-06-04](https://bellard.org/quickjs/quickjs-2026-06-04.tar.xz) release sources were compared for this study.

In the historical build, `CONFIG_BIGNUM` compiled the extension, and `qjs --bignum` activated it. An embedder could initialize operator support with `JS_AddIntrinsicOperators(ctx)`. An operator set attached to a prototype could dispatch arithmetic to native binding functions. This was a QuickJS extension, not portable JavaScript, and even that extension did not overload `[]`.

Current `Symbol.toPrimitive`, `valueOf`, and `Proxy` mechanisms do not restore vector-valued arithmetic. Primitive conversion must produce a primitive; it cannot make `a + b` return a new wrapped `Vec3`. Object-to-object `===` compares identity, and object-to-object `==` does not call a custom C++ equality operator. See the ECMAScript algorithms for [ToPrimitive](https://tc39.es/ecma262/2025/multipage/abstract-operations.html#sec-toprimitive), [addition](https://tc39.es/ecma262/2025/multipage/ecmascript-language-expressions.html#sec-addition-operator-plus), and [equality](https://tc39.es/ecma262/2025/multipage/abstract-operations.html#sec-islooselyequal).

For a current QuickJS backend, expose the existing C++ operators through named methods. Suggested mapping, subject to an API naming/collision review:

| C++ / existing script operation | Proposed JavaScript equivalent | Semantics |
| --- | --- | --- |
| `a + b`, `a - b` | `a.add(b)`, `a.sub(b)` | Return a new value |
| `a * b`, `a / b` | `a.mul(b)`, `a.div(b)` | Dispatch only the overloads actually bound for that type |
| `a += b`, `a *= b` | `a.addAssign(b)`, `a.mulAssign(b)` | Mutate the receiver; document the return convention |
| C++ value equality | `a.equals(b)` | Call the declared native comparison |
| Ordering operators | `a.lessThan(b)`, etc. | Generate only where the binding declares them |

```javascript
// Proposed current-QuickJS API, not an existing Harfang JavaScript binding.
const position = new hg.Vec3(1, 2, 3);
const velocity = new hg.Vec3(0, 1, 0);
const next = position.add(velocity.mul(0.016));
```

FABGen can still dispatch overloaded C++ functions and constructors by argument count and type. Function overload dispatch and JavaScript operator syntax are separate issues.

If literal `Vec3 + Vec3` or `Mat4 * Vec3` syntax is mandatory, current unmodified QuickJS does **not** meet that requirement. The alternatives are an old pinned runtime, a maintained interpreter fork restoring the extension, or a source transformation layer. Each changes the maintenance scope substantially; none should be hidden inside the binding effort estimate.

## Executive Summary

Adding QuickJS to Harfang is technically feasible, but reaching production coverage comparable to Lua is a medium-to-large integration project. FABGen needs a new backend, and the engine needs JavaScript-specific value ownership, scene instance semantics, and job scheduling.

The recommended target is:

- Current official QuickJS, pinned to a reviewed release, with named methods for C++ operators.
- A Harfang launcher, provisionally `hg_quickjs`, registering a native ES module named `harfang`.
- A new `SceneQuickJSVM`, with the same lifecycle capabilities as `SceneLuaVM` and an explicitly documented JavaScript script-instance contract.
- Generated public and embedded bindings from the shared `binding/bind_harfang.py` declarations.
- Runtime source loading from Harfang's compiled asset namespace before optional bytecode packaging.

The main qualification is **functional coverage, not identical syntax or value semantics**. JavaScript has one return value, identity-based object equality, a distinct `BigInt` type, and lexical/module bindings that are not writable environment-table slots. These differences require deliberate API rules.

The principal early gates are operator ergonomics, the Windows toolchain, and safe ownership of native objects and callbacks. A JavaScript vector demo alone would not establish full Harfang feasibility.

## Current Lua Integration In Harfang

The existing architecture still provides three useful reference layers:

1. `harfang/script/lua_vm.*`: VM creation, compilation, calls, registry references, stack management, and interruption support.
2. `harfang/engine/lua_object.*`: opaque script values and transfer of primitives or FABGen-wrapped C++ objects between VMs.
3. `harfang/engine/scene_lua_vm.*` and `scene_systems.*`: per-component script environments, shared `G`, injected `hg`, script parameters, and scene/node lifecycle dispatch.

`binding/CMakeLists.txt` generates the embedded Lua binding with `--lua --embedded --prefix hg_lua`. The engine links this binding and the script library. `languages/hg_lua` provides the public language package. `assetc` recognizes Lua and has a dedicated source/bytecode processing path.

The repository has advanced since the reference Squirrel feasibility document: FABGen now has `lang/squirrel.py`, primitive/STL converters, CLI selection, and test support. Harfang has a public `languages/hg_squirrel` package, launchers, and `.nut` asset handling. These are useful additional references for adding a backend and packaging it.

However, the inspected engine still uses `SceneLuaVM`; no `SceneSquirrelVM` or `SceneQuickJSVM` implementation was found. The public Squirrel binding includes adapters to the Lua scene VM. Public language support and native scene execution in that language must therefore be treated as distinct deliverables.

`Scene::Script_` still stores a path and a map of `ScriptParam` values without a language discriminator. `ScriptParam` supports null, boolean, native `int`, `float`, and string; arbitrary JavaScript objects and `BigInt` parameters are not already covered by scene serialization.

## QuickJS Fit

### Runtime And Native Binding Model

QuickJS is a small C interpreter with an MIT license and broad ECMAScript support. Its executable compiler packages bytecode with a runtime; it does not turn a Harfang script into optimized native machine code or provide a JIT. The [official overview](https://bellard.org/quickjs/) and [manual](https://bellard.org/quickjs/quickjs.html) describe the runtime and packaging model.

The release's `quickjs.h` exposes the mechanisms needed for the integration:

| Requirement | QuickJS API / mechanism |
| --- | --- |
| Runtime and context lifecycle | `JS_NewRuntime`, `JS_NewContext`, `JS_FreeContext`, `JS_FreeRuntime` |
| Compile, evaluate, call | `JS_Eval`, `JS_EvalFunction`, `JS_Call` |
| Retain and release values | `JS_DupValue`, `JS_FreeValue` |
| Native classes and payloads | `JS_NewClassID`, `JS_NewClass`, `JS_NewObjectClass`, `JS_SetOpaque`, `JS_GetOpaque2` |
| Methods and accessors | `JS_NewCFunction`, `JS_SetPropertyFunctionList` |
| Native modules | `JS_NewCModule`, `JS_AddModuleExport`, `JS_SetModuleExport` |
| Asset-aware imports | `JS_SetModuleLoaderFunc` and normalization callbacks |
| Exceptions | `JS_EXCEPTION`, `JS_IsException`, `JS_GetException`, `JS_ThrowTypeError` |
| Promise jobs and rejection reporting | `JS_ExecutePendingJob`, `JS_SetHostPromiseRejectionTracker` |
| Runtime limits | `JS_SetMemoryLimit`, `JS_SetMaxStackSize`, `JS_SetInterruptHandler` |

This is a handle-based C API, not a Lua/Squirrel stack API. A typical generated function has this shape:

```cpp
static JSValue proxy(JSContext *ctx, JSValueConst this_val,
                     int argc, JSValueConst *argv);
```

Use a native QuickJS class with an opaque FABGen payload as the default representation. The official `examples/point.c` demonstrates constructors, payloads, finalizers, methods, and accessors. Do not put a JavaScript `Proxy` around every native object without a specific need and measurement. Sources: [release archive](https://bellard.org/quickjs/quickjs-2026-06-04.tar.xz), [C API header](https://github.com/bellard/quickjs/blob/master/quickjs.h), and [class example](https://github.com/bellard/quickjs/blob/master/examples/point.c).

### Ownership And Runtime Boundaries

A QuickJS value wrapper must distinguish adopting an owned result from duplicating a borrowed argument. Property setters and several other APIs consume values; a uniform convention and generated cleanup paths are essential. Temporary UTF-8 strings from `JS_ToCStringLen` also need release, including on conversion failure.

Recommended ownership rules for the Harfang integration:

- Copy an owned value with `JS_DupValue`; release it exactly once. All handles must be cleared before their context/runtime is destroyed, or hold a runtime owner that guarantees this ordering.
- Separate native value copies, owned allocations, borrowed references, and shared ownership. A finalizer must not delete a borrowed engine object.
- Keep a parent alive for a reference into its storage, or reject use after invalidation. Scene deletion and resource destruction need explicit invalidation behavior.
- If a native payload owns JavaScript values, expose those edges through the class `gc_mark` callback and `JS_MarkValue`. A hidden C++/JavaScript ownership cycle will not resolve itself.
- Release registered C++ callbacks before VM teardown. A captured `JSValue` in an arbitrary `std::function` needs a lifetime design beyond reference counting.
- Keep rendering and scene callbacks on the runtime's owning thread. Marshal work from other threads; do not enter the same runtime concurrently.

QuickJS contexts in one runtime can share objects, but separate runtimes cannot share `JSValue` objects. A public launcher and an embedded scene VM using different runtimes therefore need explicit primitive conversion and native-payload rewrapping. JavaScript functions, closures, prototypes, and arbitrary object graphs should not be promised as automatically transferable. The runtime and finalizer constraints are documented in the [C API manual](https://bellard.org/quickjs/quickjs.html#QuickJS-C-API).

### Windows And Build Compatibility

Harfang uses CMake and a C++14 baseline, with Windows/MSVC paths. Official QuickJS ships a Makefile using GCC/Clang conventions; its Windows paths target MinGW, including an MSYS environment. There is no ready-made official CMake/MSVC target in the inspected archive. C++14 compatibility alone does not establish that the C runtime or header macros compile cleanly with MSVC.

The first build spike should compile the runtime as C, compile one generated wrapper as Harfang C++, and link both into the actual Windows configuration. Test Debug and Release, allocator boundaries, exceptions, runtime library selection, and the same build arrangement on Linux. Reproduce relevant upstream compiler flags/configuration rather than merely listing the `.c` files in CMake.

A Clang-based build or a separate C runtime library may be viable, but it must be proven with Harfang's toolchain. Do not assume a MinGW-built C++ Harfang binding can be substituted into an MSVC C++ build. If a QuickJS-NG evaluation becomes desirable for build-system reasons, make it a separate, explicit runtime decision. Evidence: the release `Makefile` and the manual's [installation section](https://bellard.org/quickjs/quickjs.html#Installation).

## Fabgen Impact

FABGen remains the largest implementation work item. Reuse its binding declarations and feature model; implement QuickJS's conversion and lifetime semantics directly.

### Required Additions

Expected new files in FABGen:

- `lang/quickjs.py`
- `lib/quickjs/__init__.py`
- `lib/quickjs/std.py`
- `lib/quickjs/stl.py`
- QuickJS test bodies and a native test host integrated with `tests.py`.

Add `--quickjs` in `bind.py`, selection in `lib.bind_defaults`, and dispatch in `lib.stl.bind_function_T`. A generator language name of `QuickJS` would follow the existing naming convention and produce `bind_QuickJS.cpp` / `bind_QuickJS.h`.

The backend must cover:

- Functions, overloads, default arguments, enums, constants, strings, pointers, and references.
- Constructors, member/static methods, member/static accessors, inheritance, and native casts.
- Ownership policies, noncopyable/moveable types, shared-pointer proxies, and native type information.
- Named arithmetic/comparison methods generated from existing operator declarations.
- Arrays/vectors, output and in/out arguments, callbacks, and reverse bindings.
- Embedded registration and a public native ES module initializer.

Do not silently skip unsupported declarations. The full Harfang binding generation should produce either a supported mapping or an actionable error with the offending API.

### Numeric Conversion And Overload Rules

Use JavaScript `Number` for floats, doubles, and suitably bounded small integers. Require finite integral input and explicit range checks for integer arguments; JavaScript conversion functions can coerce or truncate values that should not match a C++ overload.

Use JavaScript `BigInt` for exact `int64_t`, `uint64_t`, and `hg::time_ns` results. The removal of the historical bignum extensions did **not** remove standard JavaScript `BigInt`. `JS_NewBigInt64` and `JS_NewBigUint64` are available in the current header.

`Number` cannot represent every integer beyond `2^53 - 1`; that is approximately 104 days in nanoseconds. Converting all Harfang timestamps to doubles would therefore silently change API guarantees. An input converter can optionally accept a safe integral `Number`, but large or fractional numbers must not silently pass.

The release implementation of `JS_ToBigInt64` reduces large values modulo 64 bits. It is not an overflow validator. Add explicit signed/unsigned bounds validation before conversion, and design the unsigned path against APIs actually present in the pinned release. Keep output types stable instead of switching between `Number` and `BigInt` based on magnitude. Sources: `quickjs.h` and `JS_ToBigInt64Free` in `quickjs.c` in the [release archive](https://bellard.org/quickjs/quickjs-2026-06-04.tar.xz).

Document that `BigInt` and `Number` arithmetic require deliberate conversion. `OnUpdate(node, dt)` should receive exact nanoseconds as `BigInt`; `hg.time_to_sec_f(dt)` supplies a floating-point duration for vector arithmetic. Existing serialized script parameters remain limited to their current native types.

For overloads, check primitive categories, ranges, and native class/cast compatibility before conversion. Define precedence for integer versus floating-point candidates, `null` versus optional pointers, and omitted arguments versus explicit `undefined`. Avoid executing arbitrary coercion hooks repeatedly while probing overloads.

### Operators, Return Values, And Collections

`gen.py` already records arithmetic, in-place arithmetic, and comparison declarations. Register their generated native proxies as named JavaScript methods. This preserves the C++ overload definitions in `bind_harfang.py` while adapting the public syntax in one backend. Check names for conflicts with existing bound methods.

JavaScript functions return one value. Recommended FABGen convention:

- No C++ return and no outputs: `undefined`.
- One logical result: the value itself.
- Multiple results: a JavaScript array in FABGen order, with a non-void primary return first, then output/in-out values.

This permits destructuring and preserves the ordering tested by `tests/arg_out.py`. A C++ `std::vector` returned as one value remains a collection, not an implicit list of multiple function results. For a mutated in/out native object, preserve the input wrapper's identity when returning it.

Support normal JavaScript arrays for array-to-`std::vector<T>` arguments and define zero-based access for wrapped lists. Specify behavior for holes, wrong element types, and conversion failure halfway through an array. Typed arrays are useful for numeric buffers, but zero-copy views need separate guarantees for lifetime, alignment, resizing, detachment, and native vector reallocation; copying is a sound first implementation.

Object equality and validity need explicit methods. Two wrappers around the same C++ pointer are not automatically `===`, and an invalid native handle is still a truthy JavaScript object. Do not inherit Lua truthiness or native equality assumptions accidentally.

### Callbacks And Type Information

Implement `std::function<>` converters and `rbind_function` hooks around `JS_Call`, with a retained callable, a defined `this` receiver, argument/result conversion, and exception cleanup. Translate C++ exceptions at the C callback boundary; never unwind them through the interpreter.

Generate the equivalents of `hg_lua_OnCollision`, `OnUpdate_NodeCtx`, `OnUpdate_SceneCtx`, attach/detach callbacks, `OnDestroy`, and `OnSubmitSceneToForwardPipeline`, under a distinct prefix such as `hg_quickjs`.

Provide a type-info API comparable to `hg_lua_type_info`, with checks, C++ casts, and wrapping/unwrapping functions. Allocate stable class IDs and register each class once per runtime, with prototypes managed per context. Public and embedded copies of generated code must not independently invent incompatible class registries for values used in the same runtime.

### Harfang Binding Script Changes

Extend `bind_std_vector`, `expand_std_vector_proto`, startup/free code, and language-specific value converters in `binding/bind_harfang.py`. Add `bind_QuickJSObject` and `bind_quickjs_scene_vm`, and expose the new scene-system overloads.

The current file also binds `LuaObject` and `SceneLuaVM` to public languages. Decide explicitly which primitive/native-object bridges the QuickJS package provides for that existing API. Passing a JavaScript closure into an independent Lua VM is a separate interoperability feature, not an automatic consequence of adding a QuickJS backend.

## Engine Impact

### New Engine Modules

Expected new files:

- `harfang/script/quickjs_vm.h` and `.cpp`
- `harfang/engine/quickjs_object.h` and `.cpp`
- `harfang/engine/scene_quickjs_vm.h` and `.cpp`

Add optional runtime/build targets, embedded binding generation in `binding/CMakeLists.txt`, script/engine dependencies, and public packaging in `languages/hg_quickjs`. Keep the public package option separate from enabling embedded JavaScript scene execution.

Mirror the useful `SceneLuaVM` operations: source/file/asset creation, node/scene script creation, `GarbageCollect`, `DestroyScripts`, `GetScriptEnv`, `GetScriptValue`, `SetScriptValue`, `Call`, `GetScriptInterface`, `OverrideScriptSource`, and `Clear`. Adapt the value and return conventions explicitly. The existing `GarbageCollect(scene)` finds obsolete script components; QuickJS heap collection through `JS_RunGC` is a different operation.

### Script Environments

Do not mechanically replace Lua `_ENV` with a JavaScript object. Top-level lexical declarations and ES module exports do not behave like writable properties of an environment table.

Recommended starting design: one runtime/context per `SceneQuickJSVM`, one mutable environment object per `ComponentRef`, and an ES module exporting a factory. Invoke the factory for each component, even when several components reference the same file.

```javascript
// Proposed scene module contract.
export function createScript(hg, G) {
    return {
        interface: ["speed"],
        speed: 1.0,
        elapsed: 0,

        OnAttachToNode(node) {
            this.elapsed = 0;
        },

        OnUpdate(node, dt) {
            this.elapsed += hg.time_to_sec_f(dt) * this.speed;
            G.updateCount = (G.updateCount ?? 0) + 1;
        },

        OnDestroy() {
        }
    };
}
```

Store the returned object as the script environment and pass it as `this` when calling its callbacks. Apply scene parameters after factory creation and before attach callbacks. `GetScriptValue` / `SetScriptValue` operate on its properties; preserve the current `OnSetScriptValue(name)` notification convention and validate `interface` as an array of strings.

Module-level state remains shared within the context; component-specific state must live in the returned object or the factory's closure. This is an explicit adaptation of the Lua programming model. A context per component is an alternative for separate globals/realms, but adds builtins, module initialization, and cross-context testing costs. Contexts in the same runtime do not provide independent memory or execution budgets.

Module caching also affects reload. Re-evaluating the same module name must not be assumed to replace its exports. `OverrideScriptSource` needs a tested module identity/cache policy, dependency handling, and retirement of old instances. For an initial implementation, rebuilding the VM on a reload is simpler to validate than unlimited versioned modules accumulating in one context.

### Scene Dispatch And Mixed Languages

Add `SceneQuickJSVM` overloads for `SceneSyncToSystemsFromFile`, `SceneSyncToSystemsFromAssets`, `SceneUpdateSystems`, `SceneGarbageCollectSystems`, and `SceneClearSystems`. Cover the physics combinations currently bound for `ScenePhysics`, Bullet, and Tau, not just those in the older Squirrel study.

Keep traversal and attach/update/detach ordering aligned with Lua. Callback errors should identify script path, component, callback, and JavaScript stack, and follow an explicit continue/disable policy.

For the first implementation, select one scene scripting language per scene execution path. Mixed Lua/JavaScript scenes require filtering so both VMs do not try to execute every component. Extension-based routing is possible, but overridden or virtual sources complicate it; an explicit language field would additionally require scene serialization and tooling changes.

### Promises And Frame Scheduling

QuickJS exposes a pending-job queue; the embedder must integrate it into the host loop. Harfang cannot simply run the command-line standard library loop until all work finishes on every frame.

Start with synchronous scene lifecycle callbacks. Treat a returned Promise as an unsupported callback result with a useful diagnostic, rather than silently overlapping updates. If asynchronous script initialization is later supported, attachment must wait for module/factory completion.

For supported Promise use outside those callbacks, pump jobs at a documented frame boundary with both a job-count/time budget and an interrupt deadline. Install rejection reporting. A job budget alone cannot stop one infinite JavaScript job; an interrupt hook cannot preempt a blocking native Harfang call. Define teardown behavior for pending jobs, because the queue belongs to the runtime and is not automatically a per-component task scheduler.

## Public QuickJS API Shape

### Model 1: Harfang Launcher And Registered Module

Recommended first distribution: `hg_quickjs`, linked to Harfang and a pinned QuickJS runtime. Register the native module before evaluating user ES modules:

```javascript
import * as hg from "harfang";

const v = new hg.Vec3(1, 2, 3);
const scaled = v.mul(2);
console.log(scaled.x, scaled.y, scaled.z);
```

The launcher supplies module resolution, logging, argument handling, the job-pump policy, and orderly shutdown. Exposing the familiar import name does not imply Node.js compatibility: Node builtins, CommonJS `require`, browser APIs, and npm native addons are not supplied by the QuickJS core.

### Model 2: Native Module Initializer

Expose a generated initializer along these lines:

```cpp
extern "C" JSModuleDef *js_init_module_harfang(JSContext *ctx,
                                             const char *module_name);
```

Use it from both a Harfang launcher and an embedded host. On platforms supported by the stock dynamic loader, a separately built native module can expose `js_init_module` and be imported by its file path.

There is a concrete Windows limitation: in the inspected 2026-06-04 `quickjs-libc.c`, `js_module_loader_so` rejects shared-library module loading under `_WIN32`; the other implementation uses `dlopen`/`dlsym`. A stock Windows `qjs` therefore does not provide a ready-made Harfang DLL import path. Registering a linked module avoids this loader limitation; a Windows DLL loader would be additional host work. See the [standard-library source](https://github.com/bellard/quickjs/blob/master/quickjs-libc.c), checked against the pinned release archive.

All modules must use the host's compatible QuickJS runtime and value ABI. Avoid separate runtime copies inside a host and DLL that exchange `JSValue` objects. Package/compiler/runtime compatibility must be specified and tested; do not promise a stable cross-version binary extension ABI.

## Asset Compiler

`assetc` currently recognizes `.lua` and `.nut`; unknown extensions fall through to the unprocessed/copy path. JavaScript source packaging may initially use that path, but verify `.js`, `.mjs`, and imported dependencies through compiled directories and asset packages.

Recommended progression:

1. Propagate JavaScript modules through `assetc` unchanged and compile them at runtime. Production asset imports resolve from compiled/mounted assets; the explicit `FromFile` path remains a separate development/host API.
2. Add a module normalizer/loader that preserves relative imports, resolves the built-in `harfang` module, reports missing dependencies, and supports Harfang reader/providers rather than assuming filesystem access.
3. Add optional bytecode caching only after source loading, versioning, invalidation, and target compatibility are proven.

QuickJS bytecode is tied to its runtime version and is not a durable portable asset format. `qjsc -c` emits C containing bytecode, not a drop-in `.luac`-style binary asset. A custom asset compiler could use `JS_WriteObject` / `JS_ReadObject`, with an explicit format/version/build identity, dependency metadata, and target validation. Load bytecode only from trusted build output; the upstream format is not validated as an untrusted input format. See the manual's [script evaluation](https://bellard.org/quickjs/quickjs.html#Script-evaluation) and [executable generation](https://bellard.org/quickjs/quickjs.html#Executable-generation) sections.

TypeScript or operator-syntax transformation would be separate offline tooling. Plain QuickJS does not directly parse TypeScript source, and neither a `.ts` extension nor a declaration file adds arithmetic operator overloading.

## Risks And Open Questions

| Risk / decision | Consequence | Recommended treatment |
| --- | --- | --- |
| Current QuickJS has no user-defined arithmetic operators | Math scripts differ from Lua/Squirrel | Agree on named operator methods before committing to the backend |
| Windows/MSVC integration | Runtime build success does not guarantee wrapper or DLL compatibility | Prove the actual C/C++ linkage and packaging first |
| Reference ownership and native invalidation | Leaks, stale pointers, or teardown crashes | Specify ownership and callback shutdown before broad API generation |
| 64-bit numeric conversion | Silent timestamp/identifier corruption | Stable `BigInt` outputs and checked input conversion |
| Scene environment and reload semantics | Shared state, stale modules, or inaccessible parameters | Factory-created instance objects and explicit reload policy |
| Promise scheduling and callbacks | Frame overruns or callbacks after destruction | Synchronous scene callbacks first; bounded host scheduling |
| Full FABGen feature coverage | Small examples work while the real binding fails | Feature matrix plus full-binding compile and representative execution |
| Deployment assumptions | Stock Windows loading and Node libraries do not match expectations | Harfang-owned launcher and documented module contract |

Measure interpreter, binding-call, allocation, and collection costs separately. Relevant workloads are repeated `Vec3`/matrix operations, property access, small scene callbacks, array conversion, and bulk engine calls. Compare against Lua and Squirrel using the same release build and scene. Upstream JavaScript benchmark scores cannot predict Harfang frame-time behavior.

Do not run heavy finalization or collection unconditionally in every callback. Include frame-time distributions, live native-object counts, and repeated create/destroy cycles in the prototype measurements.

If downloaded scripts are a product requirement, define which native modules and Harfang capabilities they may access. Omitting `std`/`os` is a useful embedding choice, but exposing broad native engine APIs is not by itself a security boundary. This is a scope decision, not a prerequisite for running trusted project scripts.

## Effort Estimate

Planning estimate for one engineer familiar with Harfang and FABGen, targeting the current official runtime and named operator methods:

| Work item | Estimate |
| --- | ---: |
| Vendor/build integration, Windows toolchain and linkage spike | 1-2 weeks |
| VM/value ownership layer, exceptions, module-loading prototype | 1-2 weeks |
| FABGen MVP: primitives, classes, overloads, accessors, named operators | 2-3 weeks |
| FABGen broad coverage: ownership, vectors, outputs, callbacks, type info | 3-5 weeks |
| Scene VM, lifecycle/physics dispatch, parameters, tests | 2-3 weeks |
| Public launcher, asset packaging, documentation and examples | 1-2 weeks |

Subtotal: **10-17 engineer-weeks**; allow approximately **12-20 engineer-weeks** including integration contingency. These are engineering estimates, not measured delivery commitments. Toolchain findings or previously unsupported binding features can increase them.

A focused feasibility spike can fit into 1-2 weeks with a small generated subset. Maintaining an operator-extension fork, implementing TypeScript/transformation tooling, a debugger integration, mixed-language serialization, and production asynchronous scene callbacks are outside the estimate.

## Recommended Implementation Plan

1. **Set the language contract.** Confirm current QuickJS with named operators, `BigInt` for 64-bit values, multiple-result arrays, and a scene factory/environment convention. If infix operator syntax is mandatory, stop this implementation route and assess the alternatives explicitly.
2. **Prove the target toolchain.** Build the pinned runtime and a tiny C++ native class/module in Harfang's Windows configuration, then Linux. Exercise allocation, finalization, import, and exception paths.
3. **Create a minimal FABGen backend.** Generate a class with an owned and a borrowed instance, overloads, accessors, arithmetic methods, exact integer conversion, and one output-argument function.
4. **Prove scene execution.** Implement a small `SceneQuickJSVM` with two components using the same script module. Demonstrate isolated instance state, shared `G`, parameter updates, lifecycle dispatch, and useful errors.
5. **Complete the feature matrix.** Adapt existing tests for functions, inheritance/casts, operator calls, default comparison, vectors, output arguments, `std::function`, and object exchange. Add meaningful lifetime and numeric-boundary coverage.
6. **Generate and compile the full binding.** Add embedded and public registration, physics combinations, and reverse pipeline callbacks. Check unsupported APIs explicitly rather than pruning them to make the build pass.
7. **Validate representative runtime paths.** Render one scene, update transforms, dispatch collisions, load modules from compiled assets, and repeatedly tear down/recreate the VM.
8. **Package the launcher and document semantics.** Include JavaScript math examples, the `time_ns` policy, return conventions, module paths, and differences from Node/browser JavaScript.
9. **Measure and refine.** Compare frame costs, optimize demonstrated bottlenecks, and only then consider bytecode assets, richer async support, or a separate runtime/fork investigation.

### Prototype Acceptance Criteria

- Native vector arithmetic methods produce correct results; `===` and `.equals()` have documented, distinct behavior.
- Boundary values around `2^53`, signed/unsigned 64-bit limits, fractional numbers, and oversized `BigInt` inputs are handled without silent truncation.
- Repeated components have independent mutable state, parameter changes reach callbacks, and `OnDestroy` runs once through the intended destruction path.
- Owned objects are released once, borrowed objects are not deleted, parent references stay valid, and retained callbacks cannot enter a destroyed runtime.
- Exceptions include script context, execution limits stop JavaScript loops, and any enabled job pump respects the host scheduling policy.
- Imports work from compiled assets and packaged assets, including relative dependencies and missing-file errors.
- Both generated binding variants build in the supported toolchain, and a representative Harfang frame loop executes successfully.

## Conclusion

QuickJS is a credible way to add an embeddable JavaScript API and scene scripting to Harfang. Native classes, ES modules, explicit value handles, and host execution controls provide the necessary building blocks.

The decision turns first on syntax: **current official QuickJS cannot preserve Harfang's overloaded arithmetic operators**. With named math methods accepted, the remaining work is substantial but conventional runtime and binding integration. With infix vector/matrix operators required, a historical runtime, maintained fork, or transformation layer becomes a separate prerequisite.

Proceed with a pinned current runtime and a small generated Windows/scene prototype before committing to full API coverage. Use the existing Lua architecture and the now-present Squirrel backend as implementation references, while making JavaScript's ownership, numeric, module, and scheduling semantics explicit.

## Sources And Verification

Primary external sources, inspected on 2026-10-03:

- [QuickJS official website](https://bellard.org/quickjs/): release baseline and license.
- [Official changelog](https://bellard.org/quickjs/Changelog): 2025-04-26 removal of bignum extensions and later releases.
- [Current manual](https://bellard.org/quickjs/quickjs.html): embedding, modules, runtime/context boundaries, bytecode and host controls.
- [Historical Bignum Extensions documentation](https://bellard.org/quickjs/jsbignum.html): the removed operator mechanism; retained online, not a current capability statement.
- [QuickJS 2024-01-13 archive](https://bellard.org/quickjs/quickjs-2024-01-13.tar.xz): `Makefile`, `qjs.c`, `quickjs.h`, `quickjs.c`, and `doc/jsbignum.texi` checked for the historical implementation and activation path.
- [QuickJS 2025-04-26 archive](https://bellard.org/quickjs/quickjs-2025-04-26.tar.xz): operator/bignum implementation markers absent from `quickjs.h`, `quickjs.c`, and `qjs.c`.
- [QuickJS 2026-06-04 archive](https://bellard.org/quickjs/quickjs-2026-06-04.tar.xz): authoritative baseline for API, integer conversion, build system, Windows loader, and native class observations in this study. SHA-256: `b376e839b322978313d929fd20663b11ba58b75df5a46c126dd19ea2fa70ad2a`.
- [Official repository](https://github.com/bellard/quickjs): navigable [header](https://github.com/bellard/quickjs/blob/master/quickjs.h), [runtime](https://github.com/bellard/quickjs/blob/master/quickjs.c), [standard library](https://github.com/bellard/quickjs/blob/master/quickjs-libc.c), [Makefile](https://github.com/bellard/quickjs/blob/master/Makefile), and [class example](https://github.com/bellard/quickjs/blob/master/examples/point.c). These `master` links can move; the release archive defines the findings above.
- [ECMAScript 2025 specification](https://tc39.es/ecma262/2025/): standard JavaScript operator, equality, primitive-conversion, and numeric semantics.

Local sources inspected; paths below are relative to their respective repository roots:

- FABGen: `specifications/SPECS_SQUIRREL_LANG_INTEGRATION_FEASIBILITY.md`, `bind.py`, `gen.py`, `lang/lua.py`, `lang/squirrel.py`, `lib/__init__.py`, `lib/stl.py`, `tests.py`, and `tests/struct_operator_call.py`; related tests identified for the proposed coverage matrix.
- Harfang: `CMakeLists.txt`, `binding/CMakeLists.txt`, `binding/bind_harfang.py`, `languages/CMakeLists.txt`, `languages/hg_squirrel/CMakeLists.txt`, `harfang/script/CMakeLists.txt`, `harfang/engine/scene_lua_vm.h`, `harfang/engine/scene_lua_vm.cpp`, `harfang/engine/lua_object.h`, `harfang/engine/scene.h`, `harfang/engine/script_param.h`, and `tools/assetc/assetc.cpp`.

Validation performed for this document: comparison with the reference study, local source inspection, official release-source comparison for operator support, and document/link consistency checks. Build compatibility, performance, memory behavior, and the proposed scene/module contract remain prototype acceptance items rather than validated implementation results.
