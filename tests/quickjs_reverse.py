import lib


def bind_test(gen):
    gen.start('my_test')
    lib.bind_defaults(gen)
    gen.rbind_function('Call', 'int', ['int value'])
    gen.finalize()
    return gen.get_output()


def quickjs_host_transform(host):
    return host.replace('JS_FreeValue(ctx, result);', '''
            if (!failed && round == 0 && realm == 0) {
                JSValue globals = JS_GetGlobalObject(ctx);
                JSValue receiver = JS_GetPropertyStr(ctx, globals, "receiver");
                JSValue fn = JS_GetPropertyStr(ctx, globals, "callback");
                bool success = false;
                if (gen_Call(ctx, fn, receiver, 4, &success) != 14 || !success) failed = true;
                JS_FreeValue(ctx, fn);
                fn = JS_GetPropertyStr(ctx, globals, "badCallback");
                gen_Call(ctx, fn, receiver, 4, &success);
                if (success) failed = true;
                JSValue exception = JS_GetException(ctx);
                if (!JS_IsError(ctx, exception)) failed = true;
                JS_FreeValue(ctx, exception);
                JS_FreeValue(ctx, fn);
                JS_FreeValue(ctx, receiver);
                JS_FreeValue(ctx, globals);
            }
            JS_FreeValue(ctx, result);''')


test_quickjs = '''
globalThis.receiver = { base: 10 };
globalThis.callback = function(n) { return this.base + n; };
globalThis.badCallback = () => 'wrong return type';
'''
