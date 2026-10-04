import lib
import lib.stl


def bind_test(gen):
    gen.start('my_test')
    lib.bind_defaults(gen)
    gen.insert_code('''
#include <functional>
#include <thread>
#include <stdexcept>
static std::function<int()> retained;
void retain(std::function<int()> f) { retained = f; }
bool wrong_thread_rejected() {
    bool rejected = false;
    std::thread worker([&] { try { retained(); } catch (const std::runtime_error &) { rejected = true; } });
    worker.join();
    return rejected;
}
bool released_callback_rejected() {
    if (!retained) return true;
    try { retained(); } catch (const std::runtime_error &) { return true; }
    return false;
}
''', True, False)
    lib.stl.bind_function_T(gen, 'std::function<int()>')
    gen.bind_function('retain', 'void', ['std::function<int()> f'])
    gen.bind_function('wrong_thread_rejected', 'bool', [])
    gen.finalize()
    return gen.get_output()


def quickjs_host_transform(host):
    host = host.replace('#include "bind_QuickJS.h"', '#include "bind_QuickJS.h"\nextern bool released_callback_rejected();')
    host = host.replace('gen_release_my_test(ctx);', '''gen_release_my_test(ctx);
            if (!released_callback_rejected()) return 4;''')
    host = host.replace('JS_FreeContext(ctx);', '''JS_FreeContext(ctx);
            if (!released_callback_rejected()) return 5;''')
    return host


test_quickjs = '''
my_test.retain(() => 42);
assert(my_test.wrong_thread_rejected());
'''
