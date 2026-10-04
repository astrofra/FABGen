#include "bind_QuickJS.h"
#include <chrono>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>

static void report(JSContext *ctx) {
    JSValue exception = JS_GetException(ctx);
    const char *message = JS_ToCString(ctx, exception);
    std::fprintf(stderr, "%s\n", message ? message : "JavaScript exception");
    JS_FreeCString(ctx, message);
    JSValue stack = JS_GetPropertyStr(ctx, exception, "stack");
    if (!JS_IsUndefined(stack)) {
        message = JS_ToCString(ctx, stack);
        std::fprintf(stderr, "%s\n", message ? message : "");
        JS_FreeCString(ctx, message);
    }
    JS_FreeValue(ctx, stack);
    JS_FreeValue(ctx, exception);
}

int main(int argc, char **argv) {
    if (argc != 2) { std::fprintf(stderr, "Usage: %s main.js\n", argv[0]); return 2; }
    std::ifstream file(argv[1], std::ios::binary);
    if (!file) { std::fprintf(stderr, "Cannot read %s\n", argv[1]); return 2; }
    std::string source((std::istreambuf_iterator<char>(file)), {});
    JSRuntime *rt = JS_NewRuntime();
    if (!rt) return 2;
    JS_SetMemoryLimit(rt, 64 * 1024 * 1024);
    JS_SetMaxStackSize(rt, 1024 * 1024);
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    JS_SetInterruptHandler(rt, [](JSRuntime *, void *opaque) -> int {
        return std::chrono::steady_clock::now() > *static_cast<std::chrono::steady_clock::time_point *>(opaque);
    }, &deadline);
    JSContext *ctx = JS_NewContext(rt);
    if (!ctx) { JS_FreeRuntime(rt); return 2; }
    bool failed = !gen_js_init_module_example(ctx, "example");
    JSValue result = failed ? JS_EXCEPTION : JS_Eval(ctx, source.data(), source.size(), argv[1], JS_EVAL_TYPE_MODULE);
    if (JS_IsException(result)) { report(ctx); failed = true; }
    JSContext *job_ctx = nullptr;
    int jobs = 0, status = 0;
    while (!failed && jobs++ < 1000 && (status = JS_ExecutePendingJob(rt, &job_ctx)) > 0) {}
    if (status < 0) { report(job_ctx); failed = true; }
    if (JS_PromiseState(ctx, result) == JS_PROMISE_REJECTED) {
        JS_Throw(ctx, JS_PromiseResult(ctx, result));
        report(ctx); failed = true;
    }
    if (jobs >= 1000 || JS_PromiseState(ctx, result) == JS_PROMISE_PENDING) {
        std::fprintf(stderr, "Module did not finish within the job budget\n");
        failed = true;
    }
    JS_FreeValue(ctx, result);
    gen_release_example(ctx);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    return failed ? 1 : 0;
}
