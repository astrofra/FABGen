# FABGen - The FABulous binding Generator for CPython and Lua
#	Copyright (C) 2018 Emmanuel Julien

import gen


def _escape_sq_string(value):
	return value.replace('\\', '\\\\').replace('"', '\\"')


def build_index_map(name, values, filter, gen_output):
	out = 'static std::map<std::basic_string<SQChar>, SQFUNCTION> %s = {' % name
	if len(values) > 0:
		entries = [gen_output(v) for v in values if filter(v)]
		out += '\n' + ',\n'.join(entries) + '\n'
	out += '};\n\n'
	return out


class SquirrelTypeConverterCommon(gen.TypeConverter):
	def get_type_api(self, module_name):
		out = '// type API for %s\n' % self.ctype
		if self.c_storage_class:
			out += 'struct %s;\n' % self.c_storage_class
		out += 'bool %s(HSQUIRRELVM v, SQInteger idx);\n' % self.check_func
		if self.c_storage_class:
			out += 'void %s(HSQUIRRELVM v, SQInteger idx, void *obj, %s &storage);\n' % (self.to_c_func, self.c_storage_class)
		else:
			out += 'void %s(HSQUIRRELVM v, SQInteger idx, void *obj);\n' % self.to_c_func
		out += 'SQInteger %s(HSQUIRRELVM v, void *obj, OwnershipPolicy);\n' % self.from_c_func
		out += '\n'
		return out

	def to_c_call(self, in_var, out_var_p):
		out = ''
		if self.c_storage_class:
			c_storage_var = 'storage_%s' % out_var_p.replace('&', '_')
			out += '%s %s;\n' % (self.c_storage_class, c_storage_var)
			out += '%s(v, %s, (void *)%s, %s);\n' % (self.to_c_func, in_var, out_var_p, c_storage_var)
		else:
			out += '%s(v, %s, %s);\n' % (self.to_c_func, in_var, out_var_p)
		return out

	def from_c_call(self, out_var, expr, ownership):
		return '%s(v, (void *)%s, %s);\n' % (self.from_c_func, expr, ownership)

	def check_call(self, in_var):
		return '%s(v, %s)' % (self.check_func, in_var)


class SquirrelClassTypeConverter(SquirrelTypeConverterCommon):
	def is_type_class(self):
		return True

	def get_type_glue(self, gen, module_name):
		out = ''

		gen.add_include('string', True)

		all_members = self.get_all_members()
		all_methods = self.get_all_methods() + self.get_all_static_methods()

		out += build_index_map('__get_member_map_%s' % self.bound_name, all_members, lambda v: True, lambda v: '\t{_SC("%s"), %s}' % (_escape_sq_string(str(v['name'])), v['getter']))
		out += build_index_map('__set_member_map_%s' % self.bound_name, all_members, lambda v: v['setter'], lambda v: '\t{_SC("%s"), %s}' % (_escape_sq_string(str(v['name'])), v['setter']))

		if len(all_members) > 0:
			out += '''static SQInteger __get_%s_instance(HSQUIRRELVM v) {
	if (sq_gettype(v, 2) == OT_STRING) {
		const SQChar *key_cstr = nullptr;
		sq_getstring(v, 2, &key_cstr);
		std::basic_string<SQChar> key = key_cstr;

		auto i = __get_member_map_%s.find(key);
		if (i != __get_member_map_%s.end()) {
			sq_remove(v, 2);
			return i->second(v);
		}
	}

	sq_pushnull(v);
	return sq_throwobject(v);
}\n\n''' % (self.bound_name, self.bound_name, self.bound_name)

		if any(member['setter'] for member in all_members):
			out += '''static SQInteger __set_%s_instance(HSQUIRRELVM v) {
	if (sq_gettype(v, 2) == OT_STRING) {
		const SQChar *key_cstr = nullptr;
		sq_getstring(v, 2, &key_cstr);
		std::basic_string<SQChar> key = key_cstr;

		auto i = __set_member_map_%s.find(key);
		if (i != __set_member_map_%s.end()) {
			sq_remove(v, 2);
			return i->second(v);
		}
	}

	sq_pushnull(v);
	return sq_throwobject(v);
}\n\n''' % (self.bound_name, self.bound_name, self.bound_name)

		out += 'static void delete_%s(void *o) { delete (%s *)o; }\n\n' % (self.bound_name, self.ctype)

		if self._inline:
			out += '''static void delete_inline_%s(void *o) {
	using T = %s;
	((T*)o)->~T();
}\n\n''' % (self.bound_name, self.ctype)

		if self.constructor:
			out += '''static SQInteger __constructor_%s(HSQUIRRELVM v) {
	SQUserPointer self_ptr = nullptr;
	if (SQ_FAILED(sq_getinstanceup(v, 1, &self_ptr, (SQUserPointer)(uintptr_t)%s, SQTrue)))
		return SQ_ERROR;

	auto self = (wrapped_Object *)self_ptr;
	SQInteger top = sq_gettop(v);
	SQInteger factory_rval_count = %s(v);
	if (factory_rval_count == SQ_ERROR)
		return SQ_ERROR;

	if (factory_rval_count != 1 || !%s(v, -1)) {
		sq_settop(v, top);
		return sq_throwerror(v, _SC("internal error: invalid constructor result for %s"));
	}

	auto tmp = cast_to_wrapped_Object_unsafe(v, -1);
''' % (self.bound_name, self.type_tag, self.constructor['proxy_name'], self.check_func, _escape_sq_string(self.bound_name))

			if self._inline:
				out += '''\
	if (tmp->obj == (void *)tmp->inline_obj) {
		init_wrapped_Object(self, %s, (void *)self->inline_obj);
''' % self.type_tag

				if self._non_copyable and self._moveable:
					out += '		new((void *)self->inline_obj) %s(std::move(*(%s *)tmp->obj));\n' % (self.ctype, self.ctype)
				else:
					out += '		new((void *)self->inline_obj) %s(*(%s *)tmp->obj);\n' % (self.ctype, self.ctype)

				out += '''\
		self->on_delete = &delete_inline_%s;
	} else {
		*self = *tmp;
	}
''' % self.bound_name
			else:
				out += '\t*self = *tmp;\n'

			out += '''\
	tmp->on_delete = nullptr;
	tmp->obj = nullptr;
	tmp->magic_u32 = 0;

	sq_setreleasehook(v, 1, wrapped_Object_releasehook);
	sq_settop(v, top);
	return 0;
}\n\n'''
		else:
			out += '''static SQInteger __constructor_%s(HSQUIRRELVM v) {
	return sq_throwerror(v, _SC("type %s is not constructible from Squirrel"));
}\n\n''' % (self.bound_name, _escape_sq_string(self.bound_name))

		out += '''bool %s(HSQUIRRELVM v, SQInteger idx) {
	auto w = cast_to_wrapped_Object_safe(v, idx);
	if (!w)
		return false;
	return _type_tag_can_cast(w->type_tag, %s);
}\n''' % (self.check_func, self.type_tag)

		out += '''void %s(HSQUIRRELVM v, SQInteger idx, void *obj) {
	auto w = cast_to_wrapped_Object_unsafe(v, idx);
	*(void **)obj = _type_tag_cast(w->obj, w->type_tag, %s);
}\n''' % (self.to_c_func, self.type_tag)

		is_inline = False

		if self._non_copyable:
			if self._moveable:
				copy_code = 'obj = new %s(std::move(*(%s *)obj));' % (self.ctype, self.ctype)
			else:
				copy_code = 'return sq_throwerror(v, _SC("type %s is non-copyable and non-moveable"));' % _escape_sq_string(self.bound_name)
		else:
			if self._inline:
				is_inline = True
				copy_code = 'obj = new((void *)w->inline_obj) %s(*(%s *)obj);' % (self.ctype, self.ctype)
			else:
				copy_code = 'obj = new %s(*(%s *)obj);' % (self.ctype, self.ctype)

		delete_code = 'w->on_delete = &delete_%s;' % self.bound_name
		if is_inline:
			delete_code = 'w->on_delete = &delete_inline_%s;' % self.bound_name

		out += '''SQInteger %s(HSQUIRRELVM v, void *obj, OwnershipPolicy own) {
	SQInteger top = sq_gettop(v);

	sq_pushroottable(v);
	sq_pushstring(v, _SC("%s"), -1);
	if (SQ_FAILED(sq_get(v, -2))) {
		sq_settop(v, top);
		return sq_throwerror(v, _SC("module %s is not registered in the Squirrel root table"));
	}

	sq_pushstring(v, _SC("%s"), -1);
	if (SQ_FAILED(sq_get(v, -2))) {
		sq_settop(v, top);
		return sq_throwerror(v, _SC("type %s is not registered in module %s"));
	}

	if (SQ_FAILED(sq_createinstance(v, -1))) {
		sq_settop(v, top);
		return SQ_ERROR;
	}

	SQUserPointer instance_ptr = nullptr;
	if (SQ_FAILED(sq_getinstanceup(v, -1, &instance_ptr, (SQUserPointer)(uintptr_t)%s, SQFalse))) {
		sq_settop(v, top);
		return sq_throwerror(v, _SC("internal error: failed to access instance storage for %s"));
	}

	auto w = (wrapped_Object *)instance_ptr;
	if (own == Copy)
		%s
	init_wrapped_Object(w, %s, obj);
	if (own != NonOwning)
		%s
	sq_setreleasehook(v, -1, wrapped_Object_releasehook);

	sq_remove(v, -2);
	sq_remove(v, -2);
	sq_remove(v, -2);
	return 1;
}\n''' % (
			self.from_c_func,
			_escape_sq_string(module_name),
			_escape_sq_string(module_name),
			_escape_sq_string(self.bound_name),
			_escape_sq_string(self.bound_name),
			_escape_sq_string(module_name),
			self.type_tag,
			_escape_sq_string(self.bound_name),
			copy_code,
			self.type_tag,
			delete_code
		)

		out += 'static SQRESULT register_%s(HSQUIRRELVM v, SQInteger module_idx) {\n' % self.bound_name
		out += '\tSQInteger top = sq_gettop(v);\n'
		if self._inline:
			out += '\tstatic_assert(sizeof(%s) <= 16, "inline Squirrel storage exceeds 16 bytes");\n' % self.ctype
		out += '\tsq_newclass(v, SQFalse);\n'
		out += '\tSQInteger class_idx = sq_gettop(v);\n'
		out += '\tif (SQ_FAILED(sq_settypetag(v, class_idx, (SQUserPointer)(uintptr_t)%s))) {\n' % self.type_tag
		out += '\t\tsq_settop(v, top);\n'
		out += '\t\treturn SQ_ERROR;\n'
		out += '\t}\n'
		out += '\tif (SQ_FAILED(sq_setclassudsize(v, class_idx, sizeof(wrapped_Object)))) {\n'
		out += '\t\tsq_settop(v, top);\n'
		out += '\t\treturn SQ_ERROR;\n'
		out += '\t}\n\n'

		out += '\t// constructor\n'
		out += '\tsq_pushstring(v, _SC("constructor"), -1);\n'
		out += '\tsq_newclosure(v, __constructor_%s, 0);\n' % self.bound_name
		out += '\tsq_setnativeclosurename(v, -1, _SC("constructor"));\n'
		out += '\tif (SQ_FAILED(sq_newslot(v, class_idx, SQFalse))) {\n'
		out += '\t\tsq_settop(v, top);\n'
		out += '\t\treturn SQ_ERROR;\n'
		out += '\t}\n\n'

		if len(all_members) > 0:
			out += '\t// instance member lookup\n'
			out += '\tsq_pushstring(v, _SC("_get"), -1);\n'
			out += '\tsq_newclosure(v, __get_%s_instance, 0);\n' % self.bound_name
			out += '\tsq_setnativeclosurename(v, -1, _SC("_get"));\n'
			out += '\tif (SQ_FAILED(sq_newslot(v, class_idx, SQFalse))) {\n'
			out += '\t\tsq_settop(v, top);\n'
			out += '\t\treturn SQ_ERROR;\n'
			out += '\t}\n\n'

		if any(member['setter'] for member in all_members):
			out += '\t// instance member assignation\n'
			out += '\tsq_pushstring(v, _SC("_set"), -1);\n'
			out += '\tsq_newclosure(v, __set_%s_instance, 0);\n' % self.bound_name
			out += '\tsq_setnativeclosurename(v, -1, _SC("_set"));\n'
			out += '\tif (SQ_FAILED(sq_newslot(v, class_idx, SQFalse))) {\n'
			out += '\t\tsq_settop(v, top);\n'
			out += '\t\treturn SQ_ERROR;\n'
			out += '\t}\n\n'

		if len(all_methods) > 0:
			out += '\t// methods\n'
			for method in all_methods:
				out += '\tsq_pushstring(v, _SC("%s"), -1);\n' % _escape_sq_string(method['bound_name'])
				out += '\tsq_newclosure(v, %s, 0);\n' % method['proxy_name']
				out += '\tsq_setnativeclosurename(v, -1, _SC("%s"));\n' % _escape_sq_string(method['bound_name'])
				out += '\tif (SQ_FAILED(sq_newslot(v, class_idx, SQFalse))) {\n'
				out += '\t\tsq_settop(v, top);\n'
				out += '\t\treturn SQ_ERROR;\n'
				out += '\t}\n'
			out += '\n'

		out += '\tsq_push(v, module_idx);\n'
		out += '\tsq_pushstring(v, _SC("%s"), -1);\n' % _escape_sq_string(self.bound_name)
		out += '\tsq_push(v, class_idx);\n'
		out += '\tif (SQ_FAILED(sq_newslot(v, -3, SQFalse))) {\n'
		out += '\t\tsq_settop(v, top);\n'
		out += '\t\treturn SQ_ERROR;\n'
		out += '\t}\n'
		out += '\tsq_settop(v, top);\n'
		out += '\treturn SQ_OK;\n'
		out += '}\n\n'

		return out


class SquirrelPtrTypeConverter(SquirrelTypeConverterCommon):
	def get_type_glue(self, gen, module_name):
		out = '''bool %s(HSQUIRRELVM v, SQInteger idx) {
	SQObjectType type = sq_gettype(v, idx);
	return type == OT_INTEGER || type == OT_NULL;
}\n''' % self.check_func

		out += '''void %s(HSQUIRRELVM v, SQInteger idx, void *obj) {
	if (sq_gettype(v, idx) == OT_NULL) {
		*((%s*)obj) = nullptr;
		return;
	}

	SQInteger p = 0;
	sq_getinteger(v, idx, &p);
	*((%s*)obj) = (%s)p;
}\n''' % (self.to_c_func, self.ctype, self.ctype, self.ctype)

		out += '''SQInteger %s(HSQUIRRELVM v, void *obj, OwnershipPolicy) {
	auto p = *((%s*)obj);
	if (!p) {
		sq_pushnull(v);
		return 1;
	}

	sq_pushinteger(v, (SQInteger)p);
	return 1;
}\n''' % (self.from_c_func, self.ctype)
		return out


class SquirrelExternTypeConverter(SquirrelTypeConverterCommon):
	def __init__(self, type, to_c_storage_type, bound_name, module):
		super().__init__(type, to_c_storage_type, bound_name)
		self.module = module

	def get_type_api(self, module_name):
		return ''

	def to_c_call(self, in_var, out_var_p):
		out = ''
		if self.c_storage_class:
			c_storage_var = 'storage_%s' % out_var_p.replace('&', '_')
			out += '%s %s;\n' % (self.c_storage_class, c_storage_var)
			out += '(*%s)(v, %s, (void *)%s, %s);\n' % (self.to_c_func, in_var, out_var_p, c_storage_var)
		else:
			out += '(*%s)(v, %s, %s);\n' % (self.to_c_func, in_var, out_var_p)
		return out

	def from_c_call(self, out_var, expr, ownership):
		return '(*%s)(v, (void *)%s, %s);\n' % (self.from_c_func, expr, ownership)

	def get_type_glue(self, gen, module_name):
		out = '// extern type API for %s\n' % self.ctype
		if self.c_storage_class:
			out += 'struct %s;\n' % self.c_storage_class
		out += 'bool (*%s)(HSQUIRRELVM v, SQInteger idx) = nullptr;\n' % self.check_func
		if self.c_storage_class:
			out += 'void (*%s)(HSQUIRRELVM v, SQInteger idx, void *obj, %s &storage) = nullptr;\n' % (self.to_c_func, self.c_storage_class)
		else:
			out += 'void (*%s)(HSQUIRRELVM v, SQInteger idx, void *obj) = nullptr;\n' % self.to_c_func
		out += 'SQInteger (*%s)(HSQUIRRELVM v, void *obj, OwnershipPolicy) = nullptr;\n' % self.from_c_func
		out += '\n'
		return out


class SquirrelGenerator(gen.FABGen):
	default_ptr_converter = SquirrelPtrTypeConverter
	default_class_converter = SquirrelClassTypeConverter
	default_extern_converter = SquirrelExternTypeConverter

	def get_language(self):
		return 'Squirrel'

	def output_includes(self):
		super().output_includes()

		self._source += '''extern "C" {
#include "squirrel.h"
}
\n'''

	def start(self, module_name):
		super().start(module_name)

		self._header += '''extern "C" {
#include "squirrel.h"
}
\n'''

		self._source += '''\
typedef struct {
	uint32_t magic_u32; // wrapped_Object marker
	uint32_t type_tag; // wrapped pointer type tag

	void *obj;
	char inline_obj[16]; // storage for inline objects

	void (*on_delete)(void *);
} wrapped_Object;

static void init_wrapped_Object(wrapped_Object *o, uint32_t type_tag, void *obj) {
	o->magic_u32 = 0x46414221;
	o->type_tag = type_tag;

	o->obj = obj;

	o->on_delete = nullptr;
}

static wrapped_Object *cast_to_wrapped_Object_safe(HSQUIRRELVM v, SQInteger idx) {
	SQUserPointer instance_ptr = nullptr;
	if (SQ_FAILED(sq_getinstanceup(v, idx, &instance_ptr, 0, SQFalse)))
		return nullptr;

	auto w = (wrapped_Object *)instance_ptr;
	if (!w || w->magic_u32 != 0x46414221)
		return nullptr;
	return w;
}

static wrapped_Object *cast_to_wrapped_Object_unsafe(HSQUIRRELVM v, SQInteger idx) {
	SQUserPointer instance_ptr = nullptr;
	sq_getinstanceup(v, idx, &instance_ptr, 0, SQFalse);
	return (wrapped_Object *)instance_ptr;
}

static SQInteger wrapped_Object_releasehook(SQUserPointer p, SQInteger size) {
	auto w = (wrapped_Object *)p;
	if (w && w->on_delete)
		w->on_delete(w->obj);
	return 0;
}

'''

		self._source += '''
class SquirrelValueRef {
public:
	SquirrelValueRef(HSQUIRRELVM v, SQInteger idx) : vm(v) {
		sq_resetobject(&value);
		sq_resetobject(&env);

		sq_getstackobj(vm, idx, &value);
		sq_addref(vm, &value);

		if (SQ_SUCCEEDED(sq_getclosureroot(vm, idx))) {
			sq_getstackobj(vm, -1, &env);
			sq_addref(vm, &env);
			sq_poptop(vm);
		} else {
			sq_pushroottable(vm);
			sq_getstackobj(vm, -1, &env);
			sq_addref(vm, &env);
			sq_poptop(vm);
		}
	}

	~SquirrelValueRef() {
		sq_release(vm, &value);
		sq_release(vm, &env);
	}

	const HSQOBJECT &GetValue() const { return value; }
	const HSQOBJECT &GetEnv() const { return env; }

private:
	HSQUIRRELVM vm{nullptr};
	HSQOBJECT value;
	HSQOBJECT env;
};
\n'''

		self._source += self.get_binding_api_declaration()
		self._header += self.get_binding_api_declaration()

	def set_error(self, type, reason):
		return 'return sq_throwerror(v, _SC("%s"));\n' % _escape_sq_string(reason)

	def get_self(self, ctx):
		return '1'

	def get_var(self, i, ctx):
		if ctx == 'rbind_rval':
			return '-1'
		return str(i + 2)

	def open_proxy(self, name, max_arg_count, ctx):
		return 'static SQInteger %s(HSQUIRRELVM v) {\n\tSQInteger arg_count = sq_gettop(v) - 1, rval_count = 0;\n\n' % name

	def close_proxy(self, ctx):
		return '\treturn rval_count;\n}\n'

	def proxy_call_error(self, msg, ctx):
		return self.set_error('runtime', msg)

	def rval_from_nullptr(self, out_var):
		return 'sq_pushnull(v);\n++rval_count;\n'

	def rval_from_c_ptr(self, conv, out_var, expr, ownership):
		return 'rval_count += ' + conv.from_c_call(out_var, expr, ownership)

	def commit_from_c_vars(self, rvals, ctx='default'):
		return ''

	def rval_assign_arg_in_out(self, out_var, arg_in_out):
		out = 'sq_push(v, %s);\n' % arg_in_out
		out += 'rval_count += 1;\n'
		return out

	def _get_rbind_call_custom_args(self):
		return 'HSQUIRRELVM v, HSQOBJECT closure, HSQOBJECT env'

	def _prepare_rbind_call(self, rval, args):
		return '''\
SQInteger top = sq_gettop(v);
SQInteger rval_count = 1;

sq_pushobject(v, closure);
sq_pushobject(v, env);

'''

	def _rbind_call(self, rval, args, success_var):
		if rval == 'void':
			return '%s = SQ_SUCCEEDED(sq_call(v, rval_count, SQFalse, SQTrue));\n' % success_var
		return '%s = SQ_SUCCEEDED(sq_call(v, rval_count, SQTrue, SQTrue));\n' % success_var

	def _clean_rbind_call(self, rval, args):
		return 'sq_settop(v, top);\n'

	def get_binding_api_declaration(self):
		type_info_name = gen.apply_api_prefix('type_info')

		out = '''\
struct %s {
	uint32_t type_tag;
	const char *c_type;
	const char *bound_name;

	bool (*check)(HSQUIRRELVM v, SQInteger index);
	void (*to_c)(HSQUIRRELVM v, SQInteger index, void *out);
	SQInteger (*from_c)(HSQUIRRELVM v, void *obj, OwnershipPolicy policy);
};\n
''' % type_info_name

		out += '// return a type info from its type tag\n'
		out += '%s *%s(uint32_t type_tag);\n' % (type_info_name, gen.apply_api_prefix('get_bound_type_info'))
		out += '// return a type info from its type name\n'
		out += '%s *%s(const char *type);\n\n' % (type_info_name, gen.apply_api_prefix('get_c_type_info'))
		return out

	def output_binding_api(self):
		type_info_name = gen.apply_api_prefix('type_info')

		self._source += '// Note: Types using a storage class for conversion are not listed here.\n'
		self._source += 'static std::map<uint32_t, %s> __type_tag_infos;\n\n' % type_info_name

		self._source += 'static void __initialize_type_tag_infos() {\n'
		for type in self._bound_types:
			if not type.c_storage_class:
				self._source += '\t__type_tag_infos[%s] = {%s, "%s", "%s", %s, %s, %s};\n' % (type.type_tag, type.type_tag, str(type.ctype), type.bound_name, type.check_func, type.to_c_func, type.from_c_func)
		self._source += '}\n\n'

		self._source += '''\
%s *%s(uint32_t type_tag) {
	auto i = __type_tag_infos.find(type_tag);
	return i == __type_tag_infos.end() ? nullptr : &i->second;
}\n\n''' % (type_info_name, gen.apply_api_prefix('get_bound_type_info'))

		self._source += 'static std::map<std::string, %s> __type_infos;\n\n' % type_info_name

		self._source += 'static void __initialize_type_infos() {\n'
		for type in self._bound_types:
			if not type.c_storage_class:
				self._source += '\t__type_infos["%s"] = {%s, "%s", "%s", %s, %s, %s};\n' % (str(type.ctype), type.type_tag, str(type.ctype), type.bound_name, type.check_func, type.to_c_func, type.from_c_func)
		self._source += '}\n\n'

		self._source += '''\
%s *%s(const char *type) {
	auto i = __type_infos.find(type);
	return i == __type_infos.end() ? nullptr : &i->second;
}\n\n''' % (type_info_name, gen.apply_api_prefix('get_c_type_info'))

	def finalize(self):
		super().finalize()

		self.output_binding_api()

		create_module_func = gen.apply_api_prefix('create_%s' % self._name)
		bind_module_func = gen.apply_api_prefix('bind_%s' % self._name)

		self._header += '// create the module object and push it onto the stack\n'
		self._header += 'SQRESULT %s(HSQUIRRELVM v);\n' % create_module_func
		self._header += '// create the module object and register it into the interpreter root table\n'
		self._header += 'SQRESULT %s(HSQUIRRELVM v, const SQChar *symbol);\n\n' % bind_module_func

		if not self.embedded:
			self._source += '''\
#if WIN32
 #define _DLL_EXPORT_ __declspec(dllexport)
#else
 #define _DLL_EXPORT_
#endif
\n'''

		self._source += 'SQRESULT %s(HSQUIRRELVM v) {\n' % create_module_func
		self._source += '\t__initialize_type_tag_infos();\n'
		self._source += '\t__initialize_type_infos();\n\n'
		self._source += '\t// custom initialization code\n'
		self._source += self._custom_init_code
		self._source += '\n'
		self._source += '\tsq_newtable(v);\n\n'

		classes_to_register = [type for type in self._bound_types if isinstance(type, SquirrelClassTypeConverter)]
		if len(classes_to_register) > 0:
			self._source += '\t// register bound classes\n'
			self._source += '\tSQInteger module_idx = sq_gettop(v);\n'
			for type in classes_to_register:
				self._source += '\tif (SQ_FAILED(register_%s(v, module_idx)))\n' % type.bound_name
				self._source += '\t\treturn SQ_ERROR;\n'
			self._source += '\n'

		if len(self._enums) > 0:
			for name, enum in self._enums.items():
				self._source += '\t// enumeration %s\n' % name
				for enum_name, value in enum.items():
					self._source += '\tsq_pushstring(v, _SC("%s"), -1);\n' % _escape_sq_string(enum_name)
					self._source += '\tsq_pushinteger(v, (SQInteger)%s);\n' % value
					self._source += '\tif (SQ_FAILED(sq_newslot(v, -3, SQFalse)))\n'
					self._source += '\t\treturn SQ_ERROR;\n'
				self._source += '\n'

		if len(self._bound_functions) > 0:
			self._source += '\t// register global functions\n'
			for f in self._bound_functions:
				self._source += '\tsq_pushstring(v, _SC("%s"), -1);\n' % _escape_sq_string(f['bound_name'])
				self._source += '\tsq_newclosure(v, %s, 0);\n' % f['proxy_name']
				self._source += '\tsq_setnativeclosurename(v, -1, _SC("%s"));\n' % _escape_sq_string(f['bound_name'])
				self._source += '\tif (SQ_FAILED(sq_newslot(v, -3, SQFalse)))\n'
				self._source += '\t\treturn SQ_ERROR;\n'
			self._source += '\n'

		self._source += '\treturn SQ_OK;\n'
		self._source += '}\n\n'

		self._source += 'SQRESULT %s(HSQUIRRELVM v, const SQChar *symbol) {\n' % bind_module_func
		self._source += '\tif (SQ_FAILED(%s(v)))\n' % create_module_func
		self._source += '\t\treturn SQ_ERROR;\n'
		self._source += '\tsq_pushroottable(v);\n'
		self._source += '\tsq_pushstring(v, symbol, -1);\n'
		self._source += '\tsq_push(v, -3);\n'
		self._source += '\tif (SQ_FAILED(sq_newslot(v, -3, SQFalse))) {\n'
		self._source += '\t\tsq_pop(v, 2);\n'
		self._source += '\t\treturn SQ_ERROR;\n'
		self._source += '\t}\n'
		self._source += '\tsq_pop(v, 2);\n'
		self._source += '\treturn SQ_OK;\n'
		self._source += '}\n\n'

		if not self.embedded:
			self._source += 'extern "C" _DLL_EXPORT_ SQRESULT sqmodule_%s(HSQUIRRELVM v) {\n' % self._name
			self._source += '\treturn %s(v);\n' % create_module_func
			self._source += '}\n'
