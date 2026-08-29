# FABGen - The FABulous binding Generator for CPython and Lua
#	Copyright (C) 2018 Emmanuel Julien

import lang.squirrel


def bind_stl(gen):
	gen.add_include('vector', True)
	gen.add_include('string', True)
	gen.add_include('map', True)

	class SquirrelStringConverter(lang.squirrel.SquirrelTypeConverterCommon):
		def get_type_glue(self, gen, module_name):
			return 'bool %s(HSQUIRRELVM v, SQInteger idx) { return sq_gettype(v, idx) == OT_STRING; }\n' % self.check_func +\
			'''void %s(HSQUIRRELVM v, SQInteger idx, void *obj) {
	const SQChar *value = nullptr;
	sq_getstring(v, idx, &value);
	*((%s*)obj) = value;
}
''' % (self.to_c_func, self.ctype) +\
			'int %s(HSQUIRRELVM v, void *obj, OwnershipPolicy) { sq_pushstring(v, ((%s*)obj)->c_str(), -1); return 1; }\n' % (self.from_c_func, self.ctype)

	gen.bind_type(SquirrelStringConverter('std::string'))


def bind_function_T(gen, type, bound_name=None):
	class SquirrelStdFunctionConverter(lang.squirrel.SquirrelTypeConverterCommon):
		def get_type_glue(self, gen, module_name):
			function = self.ctype.scoped_typename.parts[-1].template.function

			check = '''bool %s(HSQUIRRELVM v, SQInteger idx) {
	SQObjectType type = sq_gettype(v, idx);
	return type == OT_CLOSURE || type == OT_NATIVECLOSURE;
}\n''' % self.check_func

			rval = 'void' if hasattr(function, 'void_rval') else str(function.rval)

			args = []
			if hasattr(function, 'args'):
				args = [str(arg) for arg in function.args]

			rbind_helper = '_rbind_' + self.bound_name
			parms = ['%s v%d' % (arg, idx) for idx, arg in enumerate(args)]
			gen.rbind_function(rbind_helper, rval, parms, True)

			to_c = '''\
void %s(HSQUIRRELVM v, SQInteger idx, void *obj) {
	auto ref = std::make_shared<SquirrelValueRef>(v, idx);
	*((%s*)obj) = [=](%s) -> %s {
''' % (self.to_c_func, self.ctype, ', '.join(['%s v%d' % (parm, idx) for idx, parm in enumerate(args)]), rval)

			if rval != 'void':
				to_c += '\t\treturn '
			else:
				to_c += '\t\t'

			call_args = ', '.join(['v%d' % idx for idx in range(len(args))])
			if len(args) > 0:
				to_c += '%s(v, ref->GetValue(), ref->GetEnv(), %s);\n' % (gen.apply_api_prefix(rbind_helper), call_args)
			else:
				to_c += '%s(v, ref->GetValue(), ref->GetEnv());\n' % gen.apply_api_prefix(rbind_helper)

			to_c += '''\
	};
}
'''

			from_c = '''\
SQInteger %s(HSQUIRRELVM v, void *obj, OwnershipPolicy) {
	sq_pushnull(v);
	return 1;
}
''' % self.from_c_func

			return check + to_c + from_c

	return gen.bind_type(SquirrelStdFunctionConverter(type))


class SquirrelArrayToStdVectorConverter(lang.squirrel.SquirrelTypeConverterCommon):
	def __init__(self, type, T_conv):
		native_type = 'std::vector<%s>' % T_conv.ctype
		super().__init__(type, native_type, None, native_type)
		self.T_conv = T_conv

	def get_type_glue(self, gen, module_name):
		type_ = ('%s*' % self.T_conv.ctype) if self.T_conv.ctype.is_pointer() else self.T_conv.to_c_storage_ctype

		out = '''bool %s(HSQUIRRELVM v, SQInteger idx) {
	if (sq_gettype(v, idx) != OT_ARRAY)
		return false;

	SQInteger top = sq_gettop(v);
	sq_push(v, idx);
	SQInteger array_idx = sq_gettop(v);
	SQInteger size = sq_getsize(v, array_idx);
	bool success = true;

	for (SQInteger i = 0; i < size; ++i) {
		sq_pushinteger(v, i);
		if (SQ_FAILED(sq_get(v, array_idx)) || !%s(v, -1)) {
			success = false;
			break;
		}
		sq_poptop(v);
	}

	sq_settop(v, top);
	return success;
}\n''' % (self.check_func, self.T_conv.check_func)

		out += '''void %s(HSQUIRRELVM v, SQInteger idx, void *obj) {
	auto sv = (std::vector<%s> *)obj;
	sv->clear();

	SQInteger top = sq_gettop(v);
	sq_push(v, idx);
	SQInteger array_idx = sq_gettop(v);
	SQInteger size = sq_getsize(v, array_idx);
	sv->resize(size);

	for (SQInteger i = 0; i < size; ++i) {
		sq_pushinteger(v, i);
		if (SQ_FAILED(sq_get(v, array_idx)))
			break;

		%s v_elem;
		%s(v, -1, &v_elem);
		(*sv)[size_t(i)] = %s;
		sq_poptop(v);
	}

	sq_settop(v, top);
}\n''' % (self.to_c_func, self.T_conv.ctype, type_, self.T_conv.to_c_func, self.T_conv.prepare_var_from_conv('v_elem', ''))

		out += '''SQInteger %s(HSQUIRRELVM v, void *obj, OwnershipPolicy own) {
	auto sv = (std::vector<%s> *)obj;
	sq_newarray(v, 0);

	for (size_t i = 0; i < sv->size(); ++i) {
		%s(v, &sv->at(i), Copy);
		sq_arrayappend(v, -2);
	}

	return 1;
}\n''' % (self.from_c_func, self.T_conv.ctype, self.T_conv.from_c_func)
		return out


class SquirrelTableToStdMapConverter(lang.squirrel.SquirrelTypeConverterCommon):
	def __init__(self, type, K_conv, V_conv):
		super().__init__(type, type, None, type)
		self.K_conv = K_conv
		self.V_conv = V_conv

	def get_type_glue(self, gen, module_name):
		out = '''bool %s(HSQUIRRELVM v, SQInteger idx) {
	if (sq_gettype(v, idx) != OT_TABLE)
		return false;

	SQInteger top = sq_gettop(v);
	sq_push(v, idx);
	SQInteger table_idx = sq_gettop(v);
	bool success = true;

	sq_pushnull(v);
	while (SQ_SUCCEEDED(sq_next(v, table_idx))) {
		if (!%s(v, -2) || !%s(v, -1)) {
			success = false;
			break;
		}
		sq_pop(v, 2);
	}

	sq_settop(v, top);
	return success;
}\n''' % (self.check_func, self.K_conv.check_func, self.V_conv.check_func)

		out += '''void %s(HSQUIRRELVM v, SQInteger idx, void *obj) {
	auto table = (std::map<%s, %s> *)obj;
	table->clear();

	SQInteger top = sq_gettop(v);
	sq_push(v, idx);
	SQInteger table_idx = sq_gettop(v);

	sq_pushnull(v);
	while (SQ_SUCCEEDED(sq_next(v, table_idx))) {
		%s key;
		%s value;
		%s(v, -2, &key);
		%s(v, -1, &value);
		(*table)[%s] = %s;
		sq_pop(v, 2);
	}

	sq_settop(v, top);
}\n''' % (
			self.to_c_func,
			self.K_conv.ctype,
			self.V_conv.ctype,
			self.K_conv.to_c_storage_ctype,
			self.V_conv.to_c_storage_ctype,
			self.K_conv.to_c_func,
			self.V_conv.to_c_func,
			self.K_conv.prepare_var_from_conv('key', ''),
			self.V_conv.prepare_var_from_conv('value', '')
		)

		out += '''SQInteger %s(HSQUIRRELVM v, void *obj, OwnershipPolicy own) {
	auto table = (std::map<%s, %s> *)obj;
	sq_newtable(v);

	for (const auto &entry : *table) {
		auto key = entry.first;
		auto value = entry.second;
		%s(v, &key, Copy);
		%s(v, &value, Copy);
		sq_newslot(v, -3, SQFalse);
	}

	return 1;
}\n''' % (self.from_c_func, self.K_conv.ctype, self.V_conv.ctype, self.K_conv.from_c_func, self.V_conv.from_c_func)
		return out
