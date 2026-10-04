"""QuickJS-specific exactness, lifetime and callback integration tests."""
import lib
import lib.stl
from lib.quickjs.stl import QuickJSArrayToStdVectorConverter


def bind_test(gen):
    gen.start('my_test')
    lib.bind_defaults(gen)
    gen.add_include('functional', True)
    gen.add_include('stdexcept', True)
    gen.insert_code('''
int64_t signed64(int64_t n) { return n; }
uint64_t unsigned64(uint64_t n) { return n; }
int small(int n) { return n; }
uint32_t unsigned32(uint32_t n) { return n; }
std::string text(std::string n) { return n; }
const char *ctext(const char *n) { return n; }
int pick(double) { return 2; }
int pick(int) { return 1; }
int backtrack(int, const char *) { return 1; }
int backtrack(double, int) { return 2; }
int fail_native() { throw std::runtime_error("native failure"); }
struct Child { int value = 7; };
static int live_parents = 0;
struct Parent {
    Child child;
    Parent() { ++live_parents; }
    Parent(const Parent &p) : child(p.child) { ++live_parents; }
    ~Parent() { --live_parents; }
    Child &borrow() { return child; }
    Child copy() { return child; }
};
int parents() { return live_parents; }
bool nullable(Parent *p) { return p == nullptr; }
int nonnull(Parent &p) { return p.child.value; }
void mixed(int &out, Child &child) { out = 3; child.value = 19; }
std::function<int(int)> adder(int n) { return [n](int v) { return n + v; }; }
int invoke(std::function<int(int)> f, int n) { return f(n); }
std::vector<Child> children(std::vector<Child> v) { return v; }
std::vector<int> integers(std::vector<int> v) { return v; }
''', True, False)
    for name, rval, args in [
        ('signed64', 'int64_t', ['int64_t n']), ('unsigned64', 'uint64_t', ['uint64_t n']),
        ('small', 'int', ['int n']), ('unsigned32', 'uint32_t', ['uint32_t n']),
        ('text', 'std::string', ['std::string n']), ('ctext', 'const char *', ['const char *n']),
        ('parents', 'int', []), ('fail_native', 'int', []),
    ]:
        gen.bind_function(name, rval, args)
    gen.bind_function_overloads('pick', [('int', ['double n'], []), ('int', ['int n'], [])])
    gen.bind_function_overloads('backtrack', [('int', ['int n', 'const char *s'], []), ('int', ['double n', 'int v'], [])])
    child = gen.begin_class('Child')
    gen.bind_constructor(child, [])
    gen.bind_member(child, 'int value')
    gen.end_class(child)
    parent = gen.begin_class('Parent')
    gen.bind_constructor(parent, [])
    gen.bind_member(parent, 'Child child')
    gen.bind_method(parent, 'borrow', 'Child &', [])
    gen.bind_method(parent, 'copy', 'Child', [])
    gen.end_class(parent)
    gen.bind_function('nullable', 'bool', ['Parent *p'])
    gen.bind_function('nonnull', 'int', ['Parent &p'])
    gen.bind_function('mixed', 'void', ['int &out', 'Child &child'], {'arg_out': ['out'], 'arg_in_out': ['child']})
    lib.stl.bind_function_T(gen, 'std::function<int(int)>')
    gen.bind_function('adder', 'std::function<int(int)>', ['int n'])
    gen.bind_function('invoke', 'int', ['std::function<int(int)> f', 'int n'])
    for type, conv, name in [('std::vector<Child>', child, 'children'), ('std::vector<int>', gen.get_conv('int'), 'integers')]:
        gen.bind_type(QuickJSArrayToStdVectorConverter(type, conv))
        gen.bind_function(name, type, [type + ' v'])
    gen.finalize()
    return gen.get_output()


test_quickjs = r'''
for (const n of [0n, -1n, -(1n << 63n), (1n << 63n) - 1n, (1n << 53n) + 1n]) {
    assert(my_test.signed64(n) === n);
}
for (const n of [0n, 1n, (1n << 64n) - 1n]) assert(my_test.unsigned64(n) === n);
assert(my_test.signed64(7) === 7n);
assert(my_test.unsigned64(Number.MAX_SAFE_INTEGER) === 9007199254740991n);
for (const n of [1.5, NaN, Infinity, -Infinity, 2 ** 53, "7", true, undefined]) {
    throws(() => my_test.signed64(n));
}
for (const n of [1n << 63n, -(1n << 63n) - 1n, 1n << 130n]) throws(() => my_test.signed64(n));
for (const n of [-1n, 1n << 64n, 1n << 130n]) throws(() => my_test.unsigned64(n));
assert(my_test.small(-2147483648) === -2147483648);
assert(my_test.small(2147483647) === 2147483647);
assert(my_test.unsigned32(4294967295) === 4294967295);
for (const n of [2147483648, -2147483649, 1.1, 7n]) throws(() => my_test.small(n));
throws(() => my_test.unsigned32(-1));
let coercions = 0;
throws(() => my_test.small({ valueOf() { ++coercions; return 1; } }));
assert(coercions === 0);
assert(my_test.pick(1) === 1);
assert(my_test.pick(1.25) === 2);
assert(my_test.backtrack(1, 2) === 2);
assert(my_test.text("a\0é猫") === "a\0é猫");
throws(() => my_test.ctext("a\0b"));
throws(() => my_test.fail_native(), Error);
assert(my_test.nullable(null));
throws(() => my_test.nullable(undefined));
throws(() => my_test.nonnull(null));

assert(my_test.parents() === 0);
let p = new my_test.Parent();
let child = p.borrow();
let copy = p.copy();
copy.value = 99;
assert(child.value === 7);
p = null; gc();
assert(my_test.parents() === 1 && child.value === 7);
child = null; gc();
assert(my_test.parents() === 0);
assert(copy.value === 99);
// The parent edge must participate in cycle tracing.
p = new my_test.Parent(); child = p.child; p.loop = child;
p = null; child = null; gc();
assert(my_test.parents() === 0);
let c = new my_test.Child();
let [out, same] = my_test.mixed(c);
assert(out === 3 && same === c && c.value === 19);

const add5 = my_test.adder(5);
assert(add5(4) === 9);
assert(my_test.invoke(add5, 6) === 11);
assert(my_test.invoke(v => v * 2, 6) === 12);
throws(() => my_test.invoke(() => { throw new RangeError("callback"); }, 1), RangeError);
throws(() => my_test.invoke(() => 1n, 1));
throws(() => my_test.invoke(async () => 1, 1));

let values = my_test.children([c]);
assert(Array.isArray(values) && values[0].value === 19 && values[0] !== c);
values[0].value = 24;
assert(c.value === 19);
assert(my_test.integers([1, 2, 3]).join() === '1,2,3');
throws(() => my_test.integers([1, 'bad', 3]));
throws(() => my_test.integers([1, , 3]));
let getterCalls = 0;
const array = [1, 2];
Object.defineProperty(array, 1, { get() { ++getterCalls; return 2; } });
throws(() => my_test.integers(array));
assert(getterCalls === 0);
throws(() => my_test.integers(new Proxy([1, 2], { get() { ++getterCalls; return 2; } })));
assert(getterCalls === 0);
// Standard subclass construction must respect new.target.prototype.
class Sub extends my_test.Parent { extra() { return 42; } }
let sub = new Sub();
assert(sub instanceof Sub && sub instanceof my_test.Parent && sub.extra() === 42);
sub = null; gc();
'''
