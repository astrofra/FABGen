# FABGen - The FABulous binding Generator for CPython and Lua
#	Copyright (C) 2018 Emmanuel Julien

import lang.squirrel


def bind_std(gen):
	gen.add_include('cstdint', True)

	class SquirrelBoolConverter(lang.squirrel.SquirrelTypeConverterCommon):
		def get_type_glue(self, gen, module_name):
			return 'bool %s(HSQUIRRELVM v, SQInteger idx) { return sq_gettype(v, idx) == OT_BOOL; }\n' % self.check_func +\
			'''void %s(HSQUIRRELVM v, SQInteger idx, void *obj) {
	SQBool value = SQFalse;
	sq_getbool(v, idx, &value);
	*((%s*)obj) = value == SQTrue;
}
''' % (self.to_c_func, self.ctype) +\
			'int %s(HSQUIRRELVM v, void *obj, OwnershipPolicy) { sq_pushbool(v, *((%s*)obj) ? SQTrue : SQFalse); return 1; }\n' % (self.from_c_func, self.ctype)

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
			'int %s(HSQUIRRELVM v, void *obj, OwnershipPolicy) { sq_pushinteger(v, (SQInteger)*((%s*)obj)); return 1; }\n' % (self.from_c_func, self.ctype)

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
			'int %s(HSQUIRRELVM v, void *obj, OwnershipPolicy) { sq_pushfloat(v, (SQFloat)*((%s*)obj)); return 1; }\n' % (self.from_c_func, self.ctype)

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
			'int %s(HSQUIRRELVM v, void *obj, OwnershipPolicy) { sq_pushstring(v, (*(%s*)obj), -1); return 1; }\n' % (self.from_c_func, self.ctype)

	gen.bind_type(SquirrelConstCharPtrConverter('const char *'))
