"""Public/embedded copies share class identity and clean up independently."""
import gen as core
import lib
from lang.quickjs import QuickJSGenerator


def bind_test(unused):
    files = {'shared_native.h': '''#pragma once
struct Shared { int value = 7; };
inline int &cleanups() { static int n = 0; return n; }
static int read_shared(const Shared &s) { return s.value; }
'''}
    old_prefix = core.api_prefix
    try:
        for prefix, embedded in [('left', False), ('right', True)]:
            core.api_prefix = prefix
            g = QuickJSGenerator()
            g.verbose = False
            g.embedded = embedded
            g.start('my_test')
            lib.bind_defaults(g)
            g.add_include('shared_native.h')
            c = g.begin_class('Shared', bound_name='Shared' if prefix == 'left' else 'RenamedShared')
            g.bind_constructor(c, [])
            g.bind_member(c, 'int value')
            g.end_class(c)
            g.bind_function('read_shared', 'int', ['const Shared &s'])
            g.add_custom_free_code('++cleanups();')
            g.finalize()
            output = g.get_output()
            files[prefix + '.cpp'] = output['bind_QuickJS.cpp']
            files[prefix + '.h'] = output['bind_QuickJS.h']
            files['fabgen_quickjs.h'] = output['fabgen_quickjs.h']
    finally:
        core.api_prefix = old_prefix
    return files


def quickjs_host_transform(host):
    host = host.replace('#include "bind_QuickJS.h"', '#include "left.h"\n#include "right.h"\n#include "shared_native.h"')
    host = host.replace('!gen_js_init_module_my_test(ctx, "my_test")', '!left_js_init_module_my_test(ctx, "left") || !right_js_init_module_my_test(ctx, "right")')
    host = host.replace("import * as m from 'my_test';", "import * as l from 'left'; import * as r from 'right';")
    host = host.replace('gen_release_my_test(ctx);', '''int before = cleanups();
            left_release_my_test(ctx);
            right_release_my_test(ctx);
            left_release_my_test(ctx); // idempotent
            if (cleanups() != before + 2) return 3;''')
    return host


quickjs_import = "import * as left from 'left';\nimport * as right from 'right';\n"
test_quickjs = '''
const a = new left.Shared();
assert(right.read_shared(a) === 7);
assert(left.Shared === right.RenamedShared);
const b = new right.RenamedShared();
b.value = 23;
assert(left.read_shared(b) === 23);
assert(b instanceof left.Shared);
'''
