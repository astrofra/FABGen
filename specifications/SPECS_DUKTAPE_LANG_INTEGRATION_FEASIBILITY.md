# Duktape Language Integration Feasibility

Date: 2026-10-03

Scope: integrating JavaScript through Duktape into FABGen and Harfang, with a public language package and embedded scene execution comparable in capability to Lua. This study follows the Squirrel and QuickJS studies in this directory. All new API names and examples below are proposals, not existing bindings.

Baseline: **Duktape 2.7.0**, released on **2022-02-19**, is the latest source release listed on the [official download page](https://duktape.org/download) when inspected. Local repositories inspected: FABGen `36d9d1c` and Harfang `27edc9b`. Findings are based on documentation and the official release sources; no Duktape executable, generated backend, or performance benchmark was built for this study. Development-branch features are not assumed to exist in 2.7.0.

## First Question: Does Duktape Support Operator Overloading?

**No. Duktape 2.7.0 does not provide user-defined arithmetic operator overloading.** There is no equivalent of Lua arithmetic metamethods, Squirrel arithmetic metamethods, or the historical QuickJS `Operators.create` extension.

The release implementation of addition, `duk__vm_arith_add` in `src-input/duk_js_executor.c`, converts object operands to primitives and then performs string concatenation or numeric addition. It has no dispatch mechanism for returning a user-defined vector or matrix from an overloaded arithmetic operation. Other arithmetic follows numeric conversion. This behavior can be inspected in the [versioned executor source](https://github.com/svaarala/duktape/blob/v2.7.0/src-input/duk_js_executor.c).

`valueOf`, `toString`, and the supported `Symbol.toPrimitive` hook customize conversion to a primitive; they cannot turn `a + b` into a native `Vec3` result. The partial `Proxy` implementation virtualizes supported object operations, not arithmetic operators. Object-to-object `==` and `===` do not invoke C++ value equality. See the [official feature-status page](https://wiki.duktape.org/postes5features) and the ECMAScript [addition](https://262.ecma-international.org/5.1/#sec-11.6.1) and [equality](https://262.ecma-international.org/5.1/#sec-11.9) rules.

Recommended mapping for FABGen:

| C++ / existing script operation | Proposed Duktape JavaScript API | Behavior |
| --- | --- | --- |
| `a + b`, `a - b` | `a.add(b)`, `a.sub(b)` | Return a new native value wrapper |
| `a * b`, `a / b` | `a.mul(b)`, `a.div(b)` | Dispatch the overloads actually declared for the type |
| `a += b`, `a *= b` | `a.addAssign(b)`, `a.mulAssign(b)` | Mutate the receiver; specify the return convention |
| Native value equality | `a.equals(b)` | Call the bound C++ comparison |
| Native ordering | `a.lessThan(b)`, etc. | Only expose declared operations |

```javascript
// Proposed API; ES5-compatible syntax throughout this study.
var position = new hg.Vec3(1, 2, 3);
var velocity = new hg.Vec3(0, 1, 0);
var next = position.add(velocity.mul(0.016));
```

Overloaded C++ functions and constructors remain feasible: FABGen can inspect argument count and types and select an overload. That is independent of arithmetic operator syntax.

If infix `Vec3 + Vec3` or `Mat4 * Vec3` is mandatory, unmodified Duktape does not meet the requirement. A maintained interpreter extension or source transformation would be a separate project. Ordinary TypeScript compilation or ES5 transpilation does not automatically introduce overloaded vector operators.

## Executive Summary

Duktape can host a substantial Harfang binding and an embedded scene VM. Its stack API is familiar to Lua/Squirrel embedders, its distribution is straightforward to add to a native build, and its optional debugger is useful for embedded scripting.

The main compromises are language coverage and value semantics. Duktape's stable baseline is ES5/ES5.1 with selected later features, not contemporary JavaScript. In particular, it lacks native ES modules, native `BigInt`, and native Promise/async execution comparable to QuickJS. Harfang's exact 64-bit values need a binding representation of their own.

The recommended target is:

- Duktape 2.7.0 pinned with a documented configuration and patch/update policy.
- A Harfang launcher, provisionally `hg_duktape`, providing `require("harfang")` through an explicitly initialized module loader.
- A FABGen backend generating native constructor/prototype objects, named operator methods, and exact signed/unsigned 64-bit wrappers.
- A `SceneDuktapeVM` using factory-created script instances and synchronous lifecycle callbacks.
- A C++ exception configuration suitable for FABGen's C++ temporaries, validated with the actual Windows/MSVC build.
- Source loading through compiled Harfang assets before optional bytecode caching.

Feasibility is positive if an ES5-oriented scripting surface and explicit math/integer methods are acceptable. If the objective is modern JavaScript with native `BigInt`, modules, and async syntax, the QuickJS route is a closer fit, subject to the build and integration gates identified in its companion study.

## Current Lua Integration In Harfang

Three existing layers provide the architectural reference:

1. `harfang/script/lua_vm.*`: runtime management, stack guards, rooted values, compilation, protected calls, errors, and execution watchdogs.
2. `harfang/engine/lua_object.*`: primitive conversion and transfer of FABGen-wrapped native objects between Lua VMs.
3. `harfang/engine/scene_lua_vm.*` and `scene_systems.*`: script environments indexed by `ComponentRef`, shared `G`, injected `hg`, parameters, and lifecycle dispatch.

`binding/CMakeLists.txt` generates the embedded Lua binding with `--lua --embedded --prefix hg_lua`; `languages/hg_lua` supplies the public Lua package. The scene systems call generated reverse-binding functions for updates, collisions, and attach/detach events.

The current checkout also contains a FABGen Squirrel backend, converters, tests, and the Harfang public `languages/hg_squirrel` package. These additions postdate the original Squirrel feasibility study and offer concrete references for adding another target. However, the inspected engine still executes scene scripts through `SceneLuaVM`; public Squirrel support includes bridges to that VM. A public Duktape package and native Duktape scene execution are separate deliverables.

There is no Duktape backend or scene VM in the inspected paths. `Scene::Script_` stores a path and parameters without a language field. Existing `ScriptParam` values are null, boolean, native `int`, `float`, or string; arbitrary JavaScript objects and exact 64-bit wrapper objects do not already have a scene-serialization representation.

## Duktape Fit

### Language Coverage

The [official overview](https://duktape.org/) identifies ES5/ES5.1 as the language baseline, with selected ES2015+ features, buffers, coroutines, and optional debugger support. The runtime is an interpreter; bytecode caching does not provide a JIT or native compilation of application scripts.

| Capability | Duktape 2.7.0 implication for Harfang |
| --- | --- |
| Functions, objects, prototypes, getters/setters, arrays, JSON | Sufficient for native wrappers and scene state |
| `class`, arrow functions, block-scoped `let`, destructuring | Not a supported authoring baseline; use ES5 or a tested offline transformation |
| `const` | Partial historical implementation; do not assume modern immutability or block scope |
| ES `import` / `export` | Not natively supported; use a loader such as the CommonJS extra |
| Native `BigInt` and bigint literals | Not supported; exact 64-bit values need wrappers or another explicit encoding |
| Native Promise, `async` / `await` | Not available as a native modern async model; the distribution includes a separate Promise polyfill |
| Typed arrays and `Proxy` | Available with limitations/configuration dependencies; test the operations actually used |

The feature table and the release parser/builtins must drive compatibility decisions. In particular, Duktape's partial `const` behaves largely like a writable, function-scoped `var`, and its Proxy coverage is incomplete. Source: [Post-ES5 features](https://wiki.duktape.org/postes5features). The release's `polyfills/promise.js` is explicitly a limited implementation with its own host-driven queue.

Use ES5 syntax in shipped examples, generated JavaScript helpers, and the scene contract. If TypeScript or modern JavaScript is later accepted as source input, compile it offline to a tested ES5/CommonJS target and preserve original source locations. Transpilation does not supply missing host services or repair integer precision by itself.

### Native API And Object Representation

Duktape's public API provides the necessary mechanisms:

| Requirement | API / mechanism |
| --- | --- |
| Heap lifecycle and allocator hooks | `duk_create_heap`, `duk_destroy_heap` |
| Protected compilation and execution | `duk_pcompile_lstring_filename`, `duk_peval_lstring`, `duk_pcall` |
| Method calls with an explicit receiver | `duk_pcall_method` |
| Protect a sequence of API operations | `duk_safe_call` |
| Native functions and constructors | `duk_push_c_function`, `duk_is_constructor_call`, `duk_push_this` |
| Methods, accessors, and prototypes | `duk_put_function_list`, `duk_def_prop`, `duk_set_prototype` |
| Native payload storage | Hidden Symbol properties, `duk_push_pointer`, `duk_get_pointer` |
| Persistent references | Objects/slots stored in the heap, global, or thread stash |
| Finalization and collection | `duk_set_finalizer`, `duk_gc` |
| Additional threads/global environments | `duk_push_thread`, `duk_push_thread_new_globalenv` |
| Bytecode cache | `duk_dump_function`, `duk_load_function` |
| Optional debug transport | `duk_debugger_attach` and related APIs |

These names were checked against `src/duktape.h` in the [2.7.0 archive](https://duktape.org/duktape-2.7.0.tar.xz); semantics are documented in the [API reference](https://duktape.org/api.html).

A native proxy has this shape:

```cpp
static duk_ret_t proxy(duk_context *ctx);
```

Arguments begin at stack index **0**, and `this` must be obtained separately. Overload dispatchers should be registered with `DUK_VARARGS`: registration with a fixed arity pads missing arguments and discards excess ones, hiding the original count. A normal native return is zero values (`undefined`) or one value; do not copy Lua's multiple-return convention.

Represent a native class using a constructor, prototype methods/accessors, and a hidden payload containing FABGen type identity, a C++ pointer/storage handle, and ownership information. Duktape has no QuickJS-style `JSClassID`/opaque-class registration API. Use FABGen's own type/cast registry and check the payload, not just a mutable JavaScript prototype or `instanceof` result.

Hidden Symbol keys such as `DUK_HIDDEN_SYMBOL("fabgen_payload")` are accessible through the native API. Ensure a payload belongs to the receiver itself rather than being inherited from another wrapped instance. Give the registry and hidden-key scheme a consistent identity across embedded/public generated modules in the same heap. This is a binding design, not an assumption that ordinary JavaScript objects are native-safe by default.

### Rooting, Finalizers, And Heap Boundaries

Use a heap-stash reference table to implement an owned `DuktapeObject` handle. Copying a handle creates/shares a properly counted root; clearing it releases that root. A raw stack index is temporary, and `duk_get_heapptr` returns a borrowed reference that does not keep the value alive. Keeping only that pointer after the object becomes unreachable is unsafe. See [duk_get_heapptr](https://duktape.org/api.html#duk_get_heapptr).

Define these ownership rules before generating broad bindings:

- Native values returned by copy own their storage. Borrowed engine pointers must never be deleted by their wrapper.
- References into parent-owned storage retain the parent or carry checked invalidation state.
- A finalizer is idempotent: clear the payload before native destruction and handle repeated finalization, partially constructed objects, and heap teardown.
- Finalization order cannot substitute for explicit engine shutdown. Scene callbacks and renderer/resource dependencies must be detached in a controlled order.
- A native callback retaining a JavaScript closure needs a root and an unregister path. A cycle through a C++ `std::function` and a stash root remains live until explicitly broken.
- Keep finalizers minimal and nonthrowing from the host's perspective. Do not invoke arbitrary scene lifecycle code from them.

Duktape supports object rescue and repeated finalization outside heap destruction, so treating a finalizer as an unconditional one-shot C++ destructor is incorrect. The official [finalization guide](https://wiki.duktape.org/howtofinalization) describes these cases. Prefer binding-managed native finalizers and avoid exposing unrestricted finalizer replacement as part of the Harfang scripting contract.

A heap may contain several `duk_context` threads that share values. Those are Duktape execution contexts, not independent OS threads. Enter a heap from one native thread at a time; keep graphics/scene calls on the owning engine thread. Independent heaps cannot exchange heap pointers or objects directly. Copy primitives and rewrap explicitly supported native payloads when crossing heaps, with ownership preserved. Arbitrary closures and object graphs are outside an initial cross-VM bridge. Source: the versioned [heap/thread discussion](https://github.com/svaarala/duktape/blob/v2.7.0/doc/sandboxing.rst).

### C++ Errors And Windows Build

The distribution supplies `duktape.c`, `duktape.h`, and `duk_config.h`; the configuration includes MSVC support. This gives Duktape a comparatively straightforward native-build starting point. It does not remove the need to validate Harfang's CMake, compiler flags, runtime library selection, and DLL arrangement.

The critical issue is error unwinding. Default Duktape errors use `setjmp`/`longjmp`, which can bypass C++ destructors in a generated wrapper. FABGen converters create `std::string`, `std::vector`, smart pointers, and other nontrivial temporaries, so an outer `duk_pcall` alone does not make those frames safe.

Recommended configuration: compile the runtime and binding as C++ with **`DUK_USE_CPP_EXCEPTIONS` enabled**, so interpreter error propagation unwinds C++ frames. Generate a matching configuration header; adding a command-line define while the generated header explicitly undefines it is insufficient. The release's configuration tooling uses Python 2, so pin a reproducible preparation step or check in the prepared runtime/configuration instead of assuming FABGen's Python 3 environment can regenerate it unchanged.

For MSVC, the official guide specifically calls out `/EHsc`: its `c` assumption treats `extern "C"` functions as nonthrowing. Use an appropriate model such as `/EHs` for the runtime and every C++ frame that can be crossed by an interpreter exception, including generated wrappers and reentrant callback paths. Review inherited CMake flags rather than assuming a runtime-target-only change is enough. Sources: [C++ compiler guidance](https://duktape.org/guide.html#duktape-cplusplus) and [DUK_USE_CPP_EXCEPTIONS](https://github.com/svaarala/duktape/blob/v2.7.0/config/config-options/DUK_USE_CPP_EXCEPTIONS.yaml).

Protected calls still define the host error boundary. Use them for compilation/calls and `duk_safe_call` where setup or conversion can throw before the intended call. Do not swallow Duktape's internal C++ control-transfer exception with a blanket `catch (...)`. Application exception translation must distinguish native failures from interpreter control flow and fatal errors. A fatal heap error is not permission to continue using that heap.

If the project requires a C-only Duktape build, the alternative is a deliberately structured longjmp-safe adapter with no affected C++ automatic resources. That is a different wrapper architecture and should be estimated separately.

## Fabgen Impact

### Required Additions

Expected new files:

- `lang/duktape.py`
- `lib/duktape/__init__.py`
- `lib/duktape/std.py`
- `lib/duktape/stl.py`
- Duktape test bodies and a native test host integrated with `tests.py`.

Add `--duktape` in `bind.py`, selection in `lib.bind_defaults`, and `lib.stl.bind_function_T` dispatch. A generator language name of `Duktape` follows existing output conventions: `bind_Duktape.cpp` and `bind_Duktape.h`.

The Lua and Squirrel backends are useful references for stack-oriented glue, but the generated code must account for Duktape's zero-based arguments, separate `this`, JavaScript conversion rules, single result, rooting, and exception configuration.

Required coverage includes functions/overloads, default arguments, enums/constants, pointers/references, constructors, properties, inheritance/casts, ownership policies, noncopyable/moveable types, shared-pointer proxies, collections, output arguments, callbacks, reverse calls, and type information. Unsupported declarations must fail generation clearly rather than disappear silently.

### Numeric Conversion: The Main Difference From QuickJS

Duktape 2.7.0 has no native `BigInt`. Its JavaScript numbers have double-precision semantics, even if an internal fast-integer optimization is enabled. All integers are exact only through the safe range `-(2^53 - 1)` to `2^53 - 1`; that limit corresponds to approximately 104 days of nanoseconds. Casting `hg::time_ns` or a 64-bit identifier to double can silently lose information.

Recommended public mapping:

| Native value | Proposed script representation |
| --- | --- |
| `bool` | Boolean |
| Float/double | Number, with documented nonfinite-value behavior |
| Bounded 8/16/32-bit integer | Number with finite/integral/range validation |
| `int64_t`, including `hg::time_ns` | Immutable native `hg.Int64` wrapper |
| `uint64_t` | Immutable native `hg.UInt64` wrapper |
| `long`, `size_t`, `intptr_t` | Explicit target-width-aware policy; audit these typedefs |

The wrapper should provide exact decimal parsing/formatting, comparisons, and the arithmetic required by time/identifier APIs. Do not first parse a decimal string through `Number`. Reject overflow and signed/unsigned mismatches; do not rely on unchecked C++ casts or Duktape's clamping/truncating integer getters.

```javascript
// Proposed exact-integer API; names require a collision/naming review.
var id = hg.UInt64.fromString("18446744073709551615");
var exactText = id.toString();
var duration = hg.time_from_sec(1);  // accepts a safe integral Number input
var seconds = hg.time_to_sec_f(duration);
```

Return the wrapper consistently even for small 64-bit values. Converters may accept a safe integral `Number` as input, but not an already-rounded large numeric literal. Expose a checked conversion such as `toNumberExact()` for callers who explicitly need a Number, and reject automatic numeric coercion that could silently discard precision. Define exact-wrapper overflow behavior and JSON/text serialization independently of scene `ScriptParam` storage.

`OnUpdate(node, dt)` should receive exact nanoseconds using the same `Int64` representation; existing `hg.time_to_sec_f(dt)` then provides a floating-point duration for motion calculations. A convenience seconds API can be added separately, without changing the meaning of `time_ns`.

Decimal strings or two 32-bit words are alternatives, but neither supplies ordinary exact JavaScript arithmetic. The native wrapper is the recommended compromise for API consistency. A JavaScript big-number library would add another representation and dependency; it is not equivalent to built-in `BigInt`.

### Strings And Binary Data

Duktape's ECMAScript strings use CESU-8 at the C boundary. Native Harfang text/path APIs need a deliberate UTF-8 conversion contract, including supplementary Unicode characters represented as surrogate pairs. An ASCII-only demo will not reveal this issue.

Use length-aware accessors such as `duk_get_lstring` / `duk_push_lstring`, but do not assume length-aware copying also performs encoding conversion. Add CESU-8-to-UTF-8 and UTF-8-to-CESU-8 helpers for textual APIs, define invalid/lone-surrogate handling, and test embedded NUL separately from NUL-terminated `const char *` parameters. Represent arbitrary bytes as buffers, not text. The encoding is specified in the release header and the [string documentation](https://duktape.org/guide.html#type-string).

### Operators, Outputs, And Collections

Use the arithmetic/in-place/comparison declarations already recorded in `gen.py` to register named methods. Keep the shared C++ operator definitions in `binding/bind_harfang.py`; adapt script spelling inside the backend and check method-name collisions.

Use these return rules:

- No logical result: `undefined`.
- One result: return that value.
- Multiple results: return one JavaScript array in FABGen order, with the non-void primary return first, then output/in-out values.

An ES5 caller accesses result indices or assigns them to local variables; do not document destructuring syntax as native Duktape support. A returned `std::vector` is one collection result, not an implicit multi-return. Preserve wrapper identity when returning an in/out native object that was mutated.

Convert JavaScript arrays to vectors with explicit length, hole, element-type, and failure policies. Give wrapped lists zero-based explicit accessors initially. If `list[i]` virtualization is required, assess Duktape's partial Proxy behavior and the cost of proxying; do not claim full Lua/Squirrel sequence parity automatically. Copy numeric buffers initially unless zero-copy lifetime, alignment, resize, and native reallocation constraints are established.

Overload resolution should prefer validated primitive/native categories and declared casts, not repeated coercions that may execute JavaScript getters or conversion hooks. Specify omitted arguments, `undefined`, `null`, integer-versus-float candidates, and exact-integer wrapper conversions.

Two wrappers for one native pointer are not automatically `===`, and an invalid wrapped handle remains a truthy object. Provide native equality/validity operations rather than deriving them from JavaScript truthiness or prototype identity.

### Callbacks And Type Information

Implement `std::function<>` conversion using rooted callables and a defined receiver. Reverse calls use protected invocation, convert arguments/results, and restore the value stack on success and failure. Set limits before entering script code, and attach script/component/callback context to errors.

Generate `hg_duktape` equivalents of the existing reverse callbacks: collisions, node/scene updates, attach/detach, `OnDestroy`, and `OnSubmitSceneToForwardPipeline`. Test both directions of callable conversion required by the real binding; existing backend code is a reference, not evidence that every feature is complete in every language.

Provide a type-info API comparable to `hg_lua_type_info` for checks, native casts, and wrapping/unwrapping. A raw Duktape pointer value is not a typed Harfang object. Use the native payload/type registry and preserve ownership when rewrapping across heaps or languages.

### Harfang Binding Script Changes

Extend `bind_std_vector`, `expand_std_vector_proto`, language-specific converters, startup/free code, and final backend dispatch in `binding/bind_harfang.py`. Add `bind_DuktapeObject`, `bind_duktape_scene_vm`, and the new scene-system overloads.

The current shared script exposes `LuaObject` and `SceneLuaVM` to public languages. Decide explicitly which primitive/native-object bridges the Duktape package supports for that existing surface. Passing a JavaScript closure into an independent Lua VM is additional interoperability work, not an automatic backend feature.

## Engine Impact

### New Modules And Build Targets

Expected new files:

- `harfang/script/duktape_vm.h` and `.cpp`
- `harfang/engine/duktape_object.h` and `.cpp`
- `harfang/engine/scene_duktape_vm.h` and `.cpp`

Add a pinned runtime target under `extern`, optional embedded binding generation in `binding/CMakeLists.txt`, script/engine dependencies, and `languages/hg_duktape` for the public package. Separate enabling embedded execution from building a public launcher.

Mirror the useful `SceneLuaVM` operations: source/file/asset creation, node/scene script creation, `GarbageCollect`, `DestroyScripts`, `GetScriptEnv`, `GetScriptValue`, `SetScriptValue`, `Call`, `GetScriptInterface`, `OverrideScriptSource`, and `Clear`. Document changed value/multiple-result conventions. Finding obsolete scene script components and calling `duk_gc` on the heap are different operations.

### Script Environments

Recommended first model: one heap/main context per `SceneDuktapeVM`, one mutable instance object per `ComponentRef`, and CommonJS modules exporting a factory. Call the factory for each component, including when multiple components reference the same cached module.

```javascript
// Proposed scene module; requires the configured CommonJS loader.
exports.createScript = function (hg, G) {
    return {
        "interface": ["speed"],
        speed: 1.0,
        elapsed: 0,

        OnAttachToNode: function (node) {
            this.elapsed = 0;
        },

        OnUpdate: function (node, dt) {
            this.elapsed += hg.time_to_sec_f(dt) * this.speed;
            G.updateCount = (G.updateCount || 0) + 1;
        },

        OnDestroy: function () {
        }
    };
};
```

Root the returned instance and call lifecycle methods with it as `this`. Apply scene parameters after creation and before attach. `GetScriptValue` / `SetScriptValue` address instance properties; preserve the existing `OnSetScriptValue(name)` notification and validate the `interface` list.

Module-local state is shared by components using that module. Per-component state belongs in the returned object or factory closure. This contract provides predictable mutable script state without pretending that a JavaScript scope is a Lua `_ENV` table.

A Duktape thread with a new global environment is an alternative for isolated globals, but the thread object must stay rooted and the loader/builtins need initialization in that environment. It still shares the heap and its resource budget. Separate heaps provide stronger separation but prevent direct object sharing, including a directly shared `G` object.

`OverrideScriptSource` and reload require an explicit module-cache policy. Replacing a cached export does not update closures already held by live instances. For an initial reload implementation, orderly destruction and VM reconstruction are easier to validate than partial dependency-cache invalidation. Preserve useful filenames in compilation so errors remain attributable to the asset.

### Scene Dispatch And Mixed Languages

Add `SceneDuktapeVM` overloads for `SceneSyncToSystemsFromFile`, `SceneSyncToSystemsFromAssets`, `SceneUpdateSystems`, `SceneGarbageCollectSystems`, and `SceneClearSystems`. Cover current `ScenePhysics`, Bullet, and Tau combinations and the reverse pipeline callbacks.

Preserve attach/update/collision/detach ordering and route errors through a defined continue/disable policy. Ensure destruction calls `OnDestroy` through the explicit scene path exactly once, independently of later wrapper finalization.

Initially use one scene scripting language per execution path. Mixed Lua/JavaScript components require routing so both VMs do not execute every script. File extension alone cannot distinguish a Duktape-targeted `.js` asset from a QuickJS-targeted one. A project/runtime selection or explicit language/runtime metadata is needed if both are deployed; adding a scene field also affects serialization and tooling.

### Limits, Scheduling, And Debugging

Use `DUK_USE_EXEC_TIMEOUT_CHECK` with its required `DUK_USE_INTERRUPT_COUNTER` support for a host execution deadline. It is a build-time configuration hook, not a QuickJS-style runtime setter. Once it reports a timeout, keep reporting it until control returns to the original protected call; otherwise script error handling may defeat the intended unwind. The release marks this hook experimental. Source: the versioned [timeout option](https://github.com/svaarala/duktape/blob/v2.7.0/config/config-options/DUK_USE_EXEC_TIMEOUT_CHECK.yaml).

Implement any heap memory cap through allocator callbacks and accounting, and select suitable native-stack/recursion checks. Native Harfang resource allocations need separate accounting if a global resource budget is required. An interpreter deadline cannot interrupt a blocking native call.

Keep scene lifecycle callbacks synchronous. Duktape coroutines are not OS threads and cannot freely yield across arbitrary native activation frames. They do not provide automatic async scene callbacks.

If the supplied Promise polyfill is enabled, the host must call its `Promise.runQueue()` mechanism; there is no native QuickJS pending-job API to reuse. Its limitations and scheduling behavior need review before integrating it into a frame budget. Do not drain an unbounded queue in every frame or retain jobs that can call destroyed instances. The first implementation can omit this extra entirely. Source: the versioned [Promise polyfill](https://github.com/svaarala/duktape/blob/v2.7.0/polyfills/promise.js).

Duktape's optional debugger is a practical advantage. Enabling it still requires a transport, host cooperation, source-path mapping, and a compatible client; it is not automatically Chrome DevTools or a ready-made Harfang IDE integration. Preserve filenames and stack traces first, then evaluate a local development debugger after the basic runtime works. See the [debugger documentation](https://github.com/svaarala/duktape/blob/v2.7.0/debugger/README.rst).

## Public Duktape API Shape

### Model 1: Harfang Launcher With CommonJS Loading

Recommended distribution: `hg_duktape`, linked with Harfang and a pinned Duktape configuration. Initialize the `extras/module-node` loader and provide resolution/loading callbacks for compiled assets and linked native modules. Register `harfang` as a built-in module result.

```javascript
var hg = require("harfang");
var v = new hg.Vec3(1, 2, 3);
var scaled = v.mul(2);
print(scaled.x, scaled.y, scaled.z);
```

The launcher supplies `print` or logging, arguments, host services, and orderly shutdown. A bare Duktape 2.x heap does not already have `require`, filesystem access, or Node.js services. The name `module-node` refers to module-loading behavior, not full Node compatibility or automatic support for npm native addons.

The extra's callbacks receive module identifiers and either supply source or populate/replace exports for native modules. Initialize it once per global environment, and use asset-aware canonical module IDs rather than assuming host filesystem paths. Source: [module-node README](https://github.com/svaarala/duktape/blob/v2.7.0/extras/module-node/README.rst).

### Model 2: Native Module Initializer

Follow the recommended Duktape C module convention:

```cpp
extern "C" duk_ret_t dukopen_harfang(duk_context *ctx);
```

The initializer is invoked as a Duktape/C function, pushes a module value, and returns one result. The same generated registration can serve a linked launcher and an embedded scene VM. An optional DLL loader can discover this symbol and invoke it through a protected call.

The convention does not itself implement dynamic discovery or loading. Harfang must supply and test that host behavior for Windows and other platforms, and keep the module loaded while native functions/finalizers remain reachable. Share a compatible runtime/configuration across host and modules; do not assume separately configured copies are interchangeable. Source: the versioned [C module convention](https://github.com/svaarala/duktape/blob/v2.7.0/doc/c-module-convention.rst).

## Asset Compiler

`assetc` recognizes `.lua` and `.nut`, while unknown extensions use the unprocessed/copy path. Use that path for initial `.js` source packaging, verifying dependency files reach compiled directories and asset packages. Do not treat `.mjs` or `.ts` files as directly executable Duktape modules merely because they were copied.

Recommended sequence:

1. Package ES5/CommonJS JavaScript source unchanged through `assetc`.
2. Resolve relative imports and built-in modules with the host loader using Harfang's reader/providers and compiled/mounted asset namespace.
3. If modern JavaScript/TypeScript is required, add an explicit offline conversion step with a pinned toolchain and diagnostics. Keep authored source, generated ES5, and compiled assets separate.
4. Consider bytecode caching only after source execution and module semantics are stable.

`duk_dump_function` and `duk_load_function` can cache compiled ECMAScript functions. They do not serialize a running scene heap or arbitrary captured native state. Compile/cache module wrappers or factories before creating per-component state, then instantiate them normally at runtime.

Treat dumped bytecode as an internal build artifact with a runtime/configuration identity and dependency invalidation policy. Validate actual host/target compatibility rather than promising universal portability. Load only trusted build output; the API explicitly states that untrusted bytecode loading is memory unsafe. Keep source as the durable distribution/archive representation. Sources: [duk_dump_function](https://duktape.org/api.html#duk_dump_function), [duk_load_function](https://duktape.org/api.html#duk_load_function), and the versioned [bytecode documentation](https://github.com/svaarala/duktape/blob/v2.7.0/doc/bytecode.rst).

## Comparison With The QuickJS Study

This comparison uses Duktape 2.7.0 and the QuickJS 2026-06-04 baseline examined in [the companion study](SPECS_QUICKJS_LANG_INTEGRATION_FEASIBILITY.md); it is not a measured performance comparison.

| Dimension | Duktape 2.7.0 | QuickJS 2026-06-04 |
| --- | --- | --- |
| Custom arithmetic operators | No | No; historical extension removed |
| JavaScript baseline | ES5/ES5.1 plus selected later features | Broad modern ECMAScript support |
| Exact 64-bit script values | Binding-defined wrappers/encoding | Native `BigInt` with checked conversions |
| Modules | Optional CommonJS loader supplied/configured by host | Native ES module model plus host resolution |
| Promise/async support | Optional limited Promise polyfill; no native async/await baseline | Native features; host must pump jobs |
| Native binding API | Value stack, stashes, hidden native payloads | `JSValue` handles and registered native classes |
| Initial Windows build position | Amalgamation and MSVC-aware configuration | Official Makefile/MinGW-oriented baseline |
| C++ cleanup risk | Default longjmp requires explicit mitigation | Explicit handle cleanup and exception-boundary discipline |
| Debugging | Optional built-in debugger protocol | Separate tooling evaluation required |

For a deliberately constrained embedded language where portability, control, and native integration matter most, Duktape remains credible. For a new Harfang JavaScript interface intended to use modern syntax and existing JavaScript libraries, QuickJS has the stronger language fit. Neither current runtime satisfies infix vector/matrix operator syntax without additional work.

## Risks And Open Questions

| Risk / decision | Consequence | Recommended treatment |
| --- | --- | --- |
| ES5-oriented language surface | Modern scripts/dependencies may not parse or run | Establish a tested language profile and optional offline toolchain |
| No arithmetic overloading | Math examples need named methods | Decide before backend implementation |
| No native `BigInt` | Exact timestamps/IDs need additional API types | Implement/check `Int64` and `UInt64` from the start |
| Default longjmp and MSVC flags | C++ resources can survive failed calls incorrectly | C++ exception configuration and failure-path destructor tests |
| Rooting and finalization | Leaks, stale native pointers, double destruction | Explicit root ownership, idempotent finalizers, controlled teardown |
| CESU-8 versus UTF-8 | Non-BMP text/path corruption | Explicit text converters and Unicode round trips |
| Module caches and reload | Shared or stale component state | Instance factories and an explicit reload boundary |
| Public release cadence | Released package age affects dependency planning | Record a source/patch policy; do not infer abandonment from the release date |
| Partial Proxy and external scheduling | Unexpected collection or async semantics | Avoid depending on unvalidated behavior in the first API |

Benchmark binding calls, object allocation/finalization, property access, vector math, array conversion, and scene callback fan-out against the existing Lua/Squirrel paths. Track frame-time distributions and memory/native-resource counts through repeated create/destroy cycles. Duktape's footprint goals do not establish a Harfang performance ranking.

If untrusted scripts become a product requirement, define the exposed native capabilities and resource limits separately. The core's lack of default I/O does not make the full Harfang API a sandbox. This is a conditional product scope decision, not an extra approval gate for trusted project scripts.

## Effort Estimate

Planning estimate for one engineer familiar with Harfang and FABGen, using named operators, native exact-integer wrappers, and synchronous scene callbacks:

| Work item | Estimate |
| --- | ---: |
| Runtime/configuration, CMake/MSVC error-unwind validation | 1-2 weeks |
| VM/stack/rooting layer, protected calls, loader prototype | 1-2 weeks |
| FABGen MVP: functions, classes, overloads, named operators | 2-3 weeks |
| Broad conversions: exact integers, Unicode, ownership, vectors, outputs, callbacks | 3-5 weeks |
| Scene VM, lifecycle/physics dispatch, parameters, tests | 2-3 weeks |
| Public launcher, asset packaging, documentation and examples | 1-2 weeks |

Subtotal: **10-17 engineer-weeks**; approximately **12-20 engineer-weeks** with integration contingency. These are engineering estimates, not measured delivery commitments. The simpler runtime build does not eliminate the new backend, exact-integer, Unicode, and lifecycle work.

A narrow 1-2 week feasibility spike can resolve the main language/build/ownership gates with a small generated subset. Maintaining an operator-extension fork, implementing a modern-JavaScript toolchain, production asynchronous scene scheduling, mixed-runtime serialization, and a complete debugger UI are outside this estimate.

## Recommended Implementation Plan

1. **Set the language/API contract.** Accept ES5/CommonJS, named operators, exact 64-bit wrappers, and an explicit instance factory. If native modern JavaScript or infix math is mandatory, choose a different route before broad implementation.
2. **Prove Windows C++ unwinding.** Build the pinned configuration with Harfang's toolchain; inject conversion/callback failures while native temporaries are live. Check destructors, stack restoration, fatal-error handling, and module linkage in Debug/Release.
3. **Implement a minimal FABGen target.** Generate an owned/borrowed class, accessors, overloaded methods, arithmetic methods, one multi-result function, exact integer conversion, and Unicode strings.
4. **Prove scene instances.** Run two components from the same module with independent mutable state and shared `G`; exercise parameters, `OnSetScriptValue`, lifecycle calls, and source filenames.
5. **Complete the feature matrix.** Adapt existing tests for inheritance/casts, comparisons, operators, vectors, outputs, callbacks, and object exchange. Test both supported and rejected conversions.
6. **Compile the full Harfang bindings.** Generate embedded/public variants, add scene/physics overloads and reverse pipeline callbacks, and report unsupported declarations explicitly.
7. **Exercise representative runtime paths.** Render a scene, update transforms, dispatch collisions, load relative modules from compiled/packaged assets, and repeatedly tear down the VM.
8. **Package and document.** Ship the launcher, module contract, ES5 examples, exact-integer helpers, return conventions, Unicode behavior, and runtime differences from QuickJS/Node.js.
9. **Measure before extending.** Address demonstrated bottlenecks, then evaluate optional bytecode caching, debugger transport, or an offline modern-language pipeline.

### Prototype Acceptance Criteria

- Native vector methods return correct values; object identity, native equality, and mutation behavior are documented separately.
- Exact integers round-trip at signed/unsigned 64-bit boundaries; unsafe Numbers, fractions, overflow, and sign mismatches fail predictably.
- Non-BMP text and paths round-trip through the chosen encoding helpers; embedded NUL and invalid-surrogate handling are explicit.
- Injected interpreter/native errors restore stacks and release C++ temporaries with the chosen exception model.
- Rooted closures survive collection, released closures become collectible, and callbacks cannot enter a destroyed heap.
- Owned native payloads are destroyed once, borrowed payloads are not deleted, and inherited/invalid receiver payloads are rejected.
- Components sharing a module retain independent instance state; parameters, attach/update/detach, and `OnDestroy` follow the intended order.
- The watchdog exits a JavaScript loop through a protected boundary, including a loop with script-level error handling.
- Imports resolve consistently from compiled directories and packages, and both generated binding variants build in supported configurations.

## Conclusion

Duktape is technically suitable for embedding a Harfang scripting API, especially when a compact, controllable ES5-oriented runtime is acceptable. Its stack API and native build configuration offer a familiar starting point, and its debugger provides a useful optional development path.

The central constraints are **no user-defined arithmetic operators**, **no native `BigInt`**, and a language baseline substantially older than QuickJS's. A robust implementation therefore needs named math methods, exact integer wrappers, careful C++ unwinding/rooting, and a host-defined module/scene contract.

Proceed with a small generated Windows and scene prototype only if those API compromises fit the intended use. For a modern JavaScript-facing Harfang product, the existing QuickJS study is the more natural starting point; Duktape should be selected for concrete embedding requirements rather than assumed source compatibility with current JavaScript.

## Sources And Verification

Primary external sources inspected on 2026-10-03:

- [Official Duktape website](https://duktape.org/): scope, language baseline, native integration, and license.
- [Official downloads/releases](https://duktape.org/download): latest listed release and its publication date.
- [Duktape 2.7.0 source archive](https://duktape.org/duktape-2.7.0.tar.xz): authoritative implementation/configuration baseline. SHA-256: `90f8d2fa8b5567c6899830ddef2c03f3c27960b11aca222fa17aa7ac613c2890`. Distribution metadata identifies source commit `03d4d728f8365021de6955c649e6dcd05dcca99f`.
- [Programmer's Guide](https://duktape.org/guide.html), [API reference](https://duktape.org/api.html), and [Post-ES5 feature status](https://wiki.duktape.org/postes5features).
- Versioned [executor](https://github.com/svaarala/duktape/blob/v2.7.0/src-input/duk_js_executor.c), [C++ exception configuration](https://github.com/svaarala/duktape/blob/v2.7.0/config/config-options/DUK_USE_CPP_EXCEPTIONS.yaml), and [timeout configuration](https://github.com/svaarala/duktape/blob/v2.7.0/config/config-options/DUK_USE_EXEC_TIMEOUT_CHECK.yaml).
- Versioned [module-node loader documentation](https://github.com/svaarala/duktape/blob/v2.7.0/extras/module-node/README.rst), [C module convention](https://github.com/svaarala/duktape/blob/v2.7.0/doc/c-module-convention.rst), [Promise polyfill](https://github.com/svaarala/duktape/blob/v2.7.0/polyfills/promise.js), and [debugger documentation](https://github.com/svaarala/duktape/blob/v2.7.0/debugger/README.rst).
- [Finalization guide](https://wiki.duktape.org/howtofinalization), versioned [heap/thread and execution-limit discussion](https://github.com/svaarala/duktape/blob/v2.7.0/doc/sandboxing.rst), and [bytecode documentation](https://github.com/svaarala/duktape/blob/v2.7.0/doc/bytecode.rst).
- [ECMAScript 5.1 specification](https://262.ecma-international.org/5.1/): standard arithmetic, equality, and Number semantics.

Local sources reviewed for this study and its immediate QuickJS predecessor; paths are relative to each repository root:

- FABGen: `specifications/SPECS_SQUIRREL_LANG_INTEGRATION_FEASIBILITY.md`, `specifications/SPECS_QUICKJS_LANG_INTEGRATION_FEASIBILITY.md`, `bind.py`, `gen.py`, `lang/lua.py`, `lang/squirrel.py`, `lib/__init__.py`, `lib/stl.py`, `lib/lua/std.py`, `lib/lua/stl.py`, `lib/squirrel/std.py`, `tests.py`, and `tests/struct_operator_call.py`.
- Harfang: `CMakeLists.txt`, `binding/CMakeLists.txt`, `binding/bind_harfang.py`, `languages/hg_squirrel/CMakeLists.txt`, `harfang/script/lua_vm.h`, `harfang/script/CMakeLists.txt`, `harfang/engine/lua_object.cpp`, `harfang/engine/scene_lua_vm.h`, `harfang/engine/scene_lua_vm.cpp`, `harfang/engine/scene_systems.cpp`, `harfang/engine/scene.h`, `harfang/engine/script_param.h`, and `tools/assetc/assetc.cpp`.

Verification performed: comparison with the reference studies, official release/source inspection, local binding/scene inspection, and Markdown/source-link consistency checks. Build, memory, timing, language-conversion, and scene behavior remain prototype acceptance items, not validated implementation results.
