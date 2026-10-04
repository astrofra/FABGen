// Deliberately uses only QuickJS core, not quickjs-libc or its OS event loop.
#include "bind_QuickJS.h"
#include <chrono>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>

static void dump_error(JSContext *ctx) {
    JSValue error = JS_GetException(ctx);
    const char *text = JS_ToCString(ctx, error);
    std::fprintf(stderr, "%s\n", text ? text : "QuickJS exception");
    JS_FreeCString(ctx, text);
    JSValue stack = JS_GetPropertyStr(ctx, error, "stack");
    if (!JS_IsUndefined(stack)) {
        text = JS_ToCString(ctx, stack);
        std::fprintf(stderr, "%s\n", text ? text : "");
        JS_FreeCString(ctx, text);
    }
    JS_FreeValue(ctx, stack);
    JS_FreeValue(ctx, error);
}

static JSValue collect(JSContext *ctx, JSValueConst, int, JSValueConst *) {
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}

static int interrupt(JSRuntime *, void *opaque) {
    return std::chrono::steady_clock::now() > *static_cast<std::chrono::steady_clock::time_point *>(opaque);
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    std::ifstream input(argv[1], std::ios::binary);
    if (!input) return 2;
    std::string source((std::istreambuf_iterator<char>(input)), {});
    // Exercise fresh runtimes and distinct contexts sharing one runtime.
    for (int round = 0; round < 3; ++round) {
        JSRuntime *rt = JS_NewRuntime();
        if (!rt) return 2;
        JS_SetMemoryLimit(rt, 128 * 1024 * 1024);
        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
        JS_SetInterruptHandler(rt, interrupt, &deadline);
        for (int realm = 0; realm < 2; ++realm) {
            JSContext *ctx = JS_NewContext(rt);
            if (!ctx) return 2;
            JSValue global = JS_GetGlobalObject(ctx);
            JS_SetPropertyStr(ctx, global, "gc", JS_NewCFunction(ctx, collect, "gc", 0));
            JS_FreeValue(ctx, global);
            if (!gen_js_init_module_my_test(ctx, "my_test")) { dump_error(ctx); return 1; }
            // Native static variables intentionally survive contexts/runtimes.
            // Run the scenario once, then exercise registration/teardown again.
            const std::string script = round == 0 && realm == 0 ? source : "import * as m from 'my_test';";
            JSValue result = JS_Eval(ctx, script.c_str(), script.size(), argv[1], JS_EVAL_TYPE_MODULE);
            bool failed = JS_IsException(result);
            if (failed) dump_error(ctx);
            // Module evaluation produces a promise even for synchronous modules.
            JSContext *job_ctx = nullptr;
            int jobs = 0, status = 0;
            while (!failed && jobs++ < 1000 && (status = JS_ExecutePendingJob(rt, &job_ctx)) > 0) {}
            if (status < 0) { dump_error(job_ctx); failed = true; }
            if (JS_PromiseState(ctx, result) == JS_PROMISE_REJECTED) {
                JS_Throw(ctx, JS_PromiseResult(ctx, result));
                dump_error(ctx);
                failed = true;
            }
            if (jobs >= 1000 || JS_PromiseState(ctx, result) == JS_PROMISE_PENDING) failed = true;
            JS_FreeValue(ctx, result);
            gen_release_my_test(ctx);
            JS_RunGC(rt);
            JS_FreeContext(ctx);
            if (failed) { JS_FreeRuntime(rt); return 1; }
        }
        JS_RunGC(rt);
        JS_FreeRuntime(rt);
    }
    return 0;
}
