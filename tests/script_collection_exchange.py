import lib


def bind_test(gen):
	gen.start('my_test')

	lib.bind_defaults(gen)

	gen.add_include('map', True)
	gen.add_include('string', True)
	gen.add_include('vector', True)

	int_conv = gen.get_conv('int')
	string_conv = gen.get_conv('std::string')

	if gen.get_language() == 'Lua':
		from lib.lua import stl as lua_stl
		gen.bind_type(lua_stl.LuaTableToStdVectorConverter('std::vector<int>', int_conv))
		gen.bind_type(lua_stl.LuaTableToStdMapConverter('std::map<std::string, int>', string_conv, int_conv))
	elif gen.get_language() == 'Squirrel':
		from lib.squirrel import stl as squirrel_stl
		gen.bind_type(squirrel_stl.SquirrelArrayToStdVectorConverter('std::vector<int>', int_conv))
		gen.bind_type(squirrel_stl.SquirrelTableToStdMapConverter('std::map<std::string, int>', string_conv, int_conv))

	gen.insert_code('''\
#include <map>
#include <string>
#include <vector>

std::vector<int> extend_vector(std::vector<int> values) {
	values.push_back(7);
	return values;
}

int sum_vector(std::vector<int> values) {
	int sum = 0;
	for (auto value : values)
		sum += value;
	return sum;
}

std::map<std::string, int> make_table() {
	return {{"alpha", 2}, {"beta", 5}};
}

int sum_table(std::map<std::string, int> values) {
	return values["alpha"] + values["beta"];
}

std::map<std::string, int> mutate_table(std::map<std::string, int> values) {
	values["alpha"] += 1;
	values["gamma"] = values["beta"] + 4;
	return values;
}
''', True, False)

	gen.bind_function('extend_vector', 'std::vector<int>', ['std::vector<int> values'])
	gen.bind_function('sum_vector', 'int', ['std::vector<int> values'])
	gen.bind_function('make_table', 'std::map<std::string, int>', [])
	gen.bind_function('sum_table', 'int', ['std::map<std::string, int> values'])
	gen.bind_function('mutate_table', 'std::map<std::string, int>', ['std::map<std::string, int> values'])

	gen.finalize()
	return gen.get_output()


test_lua = '''\
my_test = require "my_test"

values = my_test.extend_vector({1, 2, 3})
assert(#values == 4)
assert(values[1] == 1)
assert(values[2] == 2)
assert(values[3] == 3)
assert(values[4] == 7)

assert(my_test.sum_vector({4, 5, 6}) == 15)

t = my_test.make_table()
assert(t.alpha == 2)
assert(t.beta == 5)

assert(my_test.sum_table({alpha = 4, beta = 6}) == 10)

u = my_test.mutate_table({alpha = 1, beta = 2})
assert(u.alpha == 2)
assert(u.gamma == 6)
'''


test_squirrel = '''\
local my_test = ::my_test;

local values = my_test.extend_vector([1, 2, 3]);
assert(values.len() == 4);
assert(values[0] == 1);
assert(values[1] == 2);
assert(values[2] == 3);
assert(values[3] == 7);

assert(my_test.sum_vector([4, 5, 6]) == 15);

local t = my_test.make_table();
assert(t.alpha == 2);
assert(t.beta == 5);

assert(my_test.sum_table({ alpha = 4, beta = 6 }) == 10);

local u = my_test.mutate_table({ alpha = 1, beta = 2 });
assert(u.alpha == 2);
assert(u.gamma == 6);
'''
