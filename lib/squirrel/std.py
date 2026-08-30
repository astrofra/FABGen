# FABGen - The FABulous binding Generator for CPython and Lua
#	Copyright (C) 2018 Emmanuel Julien

import lang.squirrel


def bind_std(gen):
	gen.add_include('cstdint', True)
	gen.add_include('string', True)

	class SquirrelBoolConverter(lang.squirrel.SquirrelTypeConverterCommon):
		def get_type_glue(self, gen, module_name):
			return 'bool %s(HSQUIRRELVM v, SQInteger idx) { return sq_gettype(v, idx) == OT_BOOL; }\n' % self.check_func +\
			'''void %s(HSQUIRRELVM v, SQInteger idx, void *obj) {
	SQBool value = SQFalse;
	sq_getbool(v, idx, &value);
	*((%s*)obj) = value == SQTrue;
}
''' % (self.to_c_func, self.ctype) +\
			'SQInteger %s(HSQUIRRELVM v, void *obj, OwnershipPolicy) { sq_pushbool(v, *((%s*)obj) ? SQTrue : SQFalse); return 1; }\n' % (self.from_c_func, self.ctype)

	gen.bind_type(SquirrelBoolConverter('bool'))

	class SquirrelIntConverter(lang.squirrel.SquirrelTypeConverterCommon):
		def get_type_glue(self, gen, module_name):
			return 'bool %s(HSQUIRRELVM v, SQInteger idx) { return sq_gettype(v, idx) == OT_INTEGER; }\n' % self.check_func +\
			'''void %s(HSQUIRRELVM v, SQInteger idx, void *obj) {
	SQInteger value = 0;
	sq_getinteger(v, idx, &value);
	*((%s*)obj) = (%s)value;
}
''' % (self.to_c_func, self.ctype, self.ctype) +\
			'SQInteger %s(HSQUIRRELVM v, void *obj, OwnershipPolicy) { sq_pushinteger(v, (SQInteger)*((%s*)obj)); return 1; }\n' % (self.from_c_func, self.ctype)

	gen.bind_type(SquirrelIntConverter('char'))
	gen.bind_type(SquirrelIntConverter('short'))
	gen.bind_type(SquirrelIntConverter('int'))
	gen.bind_type(SquirrelIntConverter('long'))
	gen.bind_type(SquirrelIntConverter('int8_t'))
	gen.bind_type(SquirrelIntConverter('int16_t'))
	gen.bind_type(SquirrelIntConverter('int32_t'))
	gen.bind_type(SquirrelIntConverter('int64_t'))
	gen.bind_type(SquirrelIntConverter('char16_t'))
	gen.bind_type(SquirrelIntConverter('char32_t'))
	gen.bind_type(SquirrelIntConverter('unsigned char'))
	gen.bind_type(SquirrelIntConverter('unsigned short'))
	gen.bind_type(SquirrelIntConverter('unsigned int'))
	gen.bind_type(SquirrelIntConverter('unsigned long'))
	gen.bind_type(SquirrelIntConverter('uint8_t'))
	gen.bind_type(SquirrelIntConverter('uint16_t'))
	gen.bind_type(SquirrelIntConverter('uint32_t'))
	gen.bind_type(SquirrelIntConverter('uint64_t'))
	gen.bind_type(SquirrelIntConverter('intptr_t'))
	gen.bind_type(SquirrelIntConverter('size_t'))

	class SquirrelDoubleConverter(lang.squirrel.SquirrelTypeConverterCommon):
		def get_type_glue(self, gen, module_name):
			return '''bool %s(HSQUIRRELVM v, SQInteger idx) {
	SQObjectType type = sq_gettype(v, idx);
	return type == OT_INTEGER || type == OT_FLOAT;
}
''' % self.check_func +\
			'''void %s(HSQUIRRELVM v, SQInteger idx, void *obj) {
	SQFloat value = 0;
	sq_getfloat(v, idx, &value);
	*((%s*)obj) = (%s)value;
}
''' % (self.to_c_func, self.ctype, self.ctype) +\
			'SQInteger %s(HSQUIRRELVM v, void *obj, OwnershipPolicy) { sq_pushfloat(v, (SQFloat)*((%s*)obj)); return 1; }\n' % (self.from_c_func, self.ctype)

	gen.bind_type(SquirrelDoubleConverter('float'))
	gen.bind_type(SquirrelDoubleConverter('double'))

	class SquirrelConstCharPtrConverter(lang.squirrel.SquirrelTypeConverterCommon):
		def __init__(self, type, to_c_storage_type=None, bound_name=None, from_c_storage_type=None):
			super().__init__(type, to_c_storage_type, bound_name, from_c_storage_type, True)

		def get_type_glue(self, gen, module_name):
			return 'struct %s { std::string s; };\n' % self.c_storage_class +\
			'bool %s(HSQUIRRELVM v, SQInteger idx) { return sq_gettype(v, idx) == OT_STRING; }\n' % self.check_func +\
			'''void %s(HSQUIRRELVM v, SQInteger idx, void *obj, %s &storage) {
	const SQChar *value = nullptr;
	sq_getstring(v, idx, &value);
	storage.s = value;
	*((%s*)obj) = storage.s.data();
}
''' % (self.to_c_func, self.c_storage_class, self.ctype) +\
			'SQInteger %s(HSQUIRRELVM v, void *obj, OwnershipPolicy) { sq_pushstring(v, (*(%s*)obj), -1); return 1; }\n' % (self.from_c_func, self.ctype)

	gen.bind_type(SquirrelConstCharPtrConverter('const char *'))

	class SquirrelAnyValueConverter(lang.squirrel.SquirrelTypeConverterCommon):
		def get_type_glue(self, gen, module_name):
			return '''\
struct %s {
	enum Kind {
		Null,
		Integer,
		Float,
		Bool,
		String,
		Object,
		Unsupported
	} kind{Null};

	SQInteger integer_value{0};
	SQFloat float_value{0};
	bool bool_value{false};
	std::string string_value;
	void *object_value{nullptr};
	uint32_t type_tag{0};
};

bool %s(HSQUIRRELVM v, SQInteger idx) { return true; }
void %s(HSQUIRRELVM v, SQInteger idx, void *obj) {
	auto value = (%s *)obj;
	*value = %s{};

	switch (sq_gettype(v, idx)) {
	case OT_NULL:
		value->kind = %s::Null;
		break;
	case OT_INTEGER:
		value->kind = %s::Integer;
		sq_getinteger(v, idx, &value->integer_value);
		break;
	case OT_FLOAT:
		value->kind = %s::Float;
		sq_getfloat(v, idx, &value->float_value);
		break;
	case OT_BOOL: {
		SQBool raw = SQFalse;
		value->kind = %s::Bool;
		sq_getbool(v, idx, &raw);
		value->bool_value = raw == SQTrue;
		break;
	}
	case OT_STRING: {
		const SQChar *raw = nullptr;
		value->kind = %s::String;
		sq_getstring(v, idx, &raw);
		value->string_value = raw;
		break;
	}
	default:
		if (auto wrapped = cast_to_wrapped_Object_safe(v, idx)) {
			value->kind = %s::Object;
			value->object_value = wrapped->obj;
			value->type_tag = wrapped->type_tag;
		} else {
			value->kind = %s::Unsupported;
		}
		break;
	}
}
SQInteger %s(HSQUIRRELVM v, void *obj, OwnershipPolicy) {
	auto value = (%s *)obj;

	switch (value->kind) {
	case %s::Null:
	case %s::Unsupported:
		sq_pushnull(v);
		return 1;
	case %s::Integer:
		sq_pushinteger(v, value->integer_value);
		return 1;
	case %s::Float:
		sq_pushfloat(v, value->float_value);
		return 1;
	case %s::Bool:
		sq_pushbool(v, value->bool_value ? SQTrue : SQFalse);
		return 1;
	case %s::String:
		sq_pushstring(v, value->string_value.c_str(), -1);
		return 1;
	case %s::Object:
		if (auto info = gen_get_bound_type_info(value->type_tag))
			return info->from_c(v, value->object_value, Copy);
		sq_pushnull(v);
		return 1;
	}

	sq_pushnull(v);
	return 1;
}
''' % (
				self.ctype,
				self.check_func,
				self.to_c_func,
				self.ctype,
				self.ctype,
				self.ctype,
				self.ctype,
				self.ctype,
				self.ctype,
				self.ctype,
				self.ctype,
				self.ctype,
				self.from_c_func,
				self.ctype,
				self.ctype,
				self.ctype,
				self.ctype,
				self.ctype,
				self.ctype,
				self.ctype,
				self.ctype
			)

	gen.bind_type(SquirrelAnyValueConverter('FABGenSquirrelValue'))
