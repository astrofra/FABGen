import lib


def bind_test(gen):
	gen.start('my_test')

	lib.bind_defaults(gen)

	# inject test code in the wrapper
	gen.insert_code('''\
struct simple_struct {
	simple_struct() : v_(-8) {}
	simple_struct(int v) : v_(v) {}
	int v_;
};
''', True, False)

	simple_struct = gen.begin_class('simple_struct')
	gen.bind_constructor_overloads(simple_struct, [
		([], []),
		(['int v_'], [])
	])
	gen.bind_member(simple_struct, 'int v_')
	gen.end_class(simple_struct)

	gen.finalize()
	return gen.get_output()


test_python = '''\
import my_test

s = my_test.simple_struct()
t = my_test.simple_struct(4)

assert s.v_ == -8
assert t.v_ == 4
'''

test_lua = '''\
my_test = require "my_test"

s = my_test.simple_struct()
t = my_test.simple_struct(4)

assert(s.v_ == -8)
assert(t.v_ == 4)
'''
