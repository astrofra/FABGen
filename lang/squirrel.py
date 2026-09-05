# FABGen - The FABulous binding Generator for CPython and Lua
#	Copyright (C) 2018 Emmanuel Julien

import gen


def _escape_sq_string(value):
	return value.replace('\\', '\\\\').replace('"', '\\"')


def _get_default_bound_name(value):
	return gen.get_symbol_default_bound_name(value)


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

		has_repr = 'repr' in self._features
		repr_feature = self._features['repr'] if has_repr else None
		has_sequence = 'sequence' in self._features
		seq = self._features['sequence'] if has_sequence else None

		all_members = self.get_all_members()
		all_static_members = self.get_all_static_members()
		all_methods = self.get_all_methods() + self.get_all_static_methods()
		has_mutable_members = any(member['setter'] for member in all_members)
		has_len_method = any(method['bound_name'] == 'len' for method in all_methods)
		comparison_ops = {op['op']: op for op in self.comparison_ops}
		has_default_deep_compare = self._supports_deep_compare and len(comparison_ops) == 0
		sq_arithmetic_metamethods = {'+': '_add', '-': '_sub', '*': '_mul', '/': '_div'}

		out += build_index_map('__get_member_map_%s' % self.bound_name, all_members, lambda v: True, lambda v: '\t{_SC("%s"), %s}' % (_escape_sq_string(str(v['name'])), v['getter']))
		out += build_index_map('__set_member_map_%s' % self.bound_name, all_members, lambda v: v['setter'], lambda v: '\t{_SC("%s"), %s}' % (_escape_sq_string(str(v['name'])), v['setter']))

		if has_repr:
			out += 'static SQInteger __tostring_%s_instance(HSQUIRRELVM v) {\n' % self.bound_name
			out += '\tstd::string repr;\n'
			out += gen._prepare_to_c_self(self, '_self')
			out += repr_feature('_self', 'repr')
			out += '\tsq_pushstring(v, repr.c_str(), -1);\n'
			out += '\treturn 1;\n'
			out += '}\n\n'

		if has_sequence:
			out += 'static SQInteger __len_%s_instance(HSQUIRRELVM v) {\n' % self.bound_name
			out += gen._prepare_to_c_self(self, '_self')
			out += '\tSQInteger size = 0;\n'
			out += seq.get_size('_self', 'size')
			out += '\tsq_pushinteger(v, size);\n'
			out += '\treturn 1;\n'
			out += '}\n\n'

			out += 'static SQInteger __nexti_%s_instance(HSQUIRRELVM v) {\n' % self.bound_name
			out += gen._prepare_to_c_self(self, '_self')
			out += '\tSQInteger size = 0;\n'
			out += seq.get_size('_self', 'size')
			out += '\tSQInteger next_idx = 0;\n'
			out += '''\
	if (sq_gettype(v, 2) == OT_NULL) {
		next_idx = 0;
	} else if (sq_gettype(v, 2) == OT_INTEGER) {
		SQInteger idx = 0;
		sq_getinteger(v, 2, &idx);
		next_idx = idx + 1;
	} else {
		return sq_throwerror(v, _SC("invalid iteration index"));
	}

	if (next_idx < 0 || next_idx >= size) {
		sq_pushnull(v);
		return 1;
	}

	sq_pushinteger(v, next_idx);
	return 1;
}\n\n'''

			out += 'static SQInteger __seq_get_%s_instance(HSQUIRRELVM v) {\n' % self.bound_name
			out += '\tSQInteger rval_count = 0;\n'
			out += gen._prepare_to_c_self(self, '_self')
			out += gen.prepare_to_c_var(0, gen.get_conv('int'), 'idx', 'getter')
			out += gen.decl_var(seq.wrapped_conv.ctype, 'rval')
			out += '\tbool error = false;\n'
			out += seq.get_item('_self', 'idx', 'rval', 'error')
			out += '''\
	if (error)
		return sq_throwerror(v, _SC("invalid lookup"));
'''
			out += gen.prepare_from_c_var({'conv': seq.wrapped_conv, 'ctype': seq.wrapped_conv.ctype, 'var': 'rval', 'is_arg_in_out': False, 'ownership': None})
			out += gen.commit_from_c_vars(['rval'])
			out += '\treturn rval_count;\n'
			out += '}\n\n'

			out += 'static SQInteger __seq_set_%s_instance(HSQUIRRELVM v) {\n' % self.bound_name
			out += '\tSQInteger rval_count = 0;\n'
			out += gen._prepare_to_c_self(self, '_self')
			out += gen.prepare_to_c_var(0, gen.get_conv('int'), 'idx', 'setter')
			out += gen.prepare_to_c_var(1, seq.wrapped_conv, 'cval', 'setter')
			out += '\tbool error = false;\n'
			out += seq.set_item('_self', 'idx', 'cval', 'error')
			out += '''\
	if (error)
		return sq_throwerror(v, _SC("invalid assignation"));
	return rval_count;
}\n\n'''

		if has_sequence or len(all_members) > 0:
			out += '''static SQInteger __get_%s_instance(HSQUIRRELVM v) {
''' % self.bound_name

			if has_sequence:
				out += '''\
	if (sq_gettype(v, 2) == OT_INTEGER)
		return __seq_get_%s_instance(v);

''' % self.bound_name

			if len(all_members) > 0:
				out += '''\
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
''' % (self.bound_name, self.bound_name)

			out += '''
	sq_pushnull(v);
	return sq_throwobject(v);
}\n\n'''

		if has_sequence or has_mutable_members:
			out += '''static SQInteger __set_%s_instance(HSQUIRRELVM v) {
''' % self.bound_name

			if has_sequence:
				out += '''\
	if (sq_gettype(v, 2) == OT_INTEGER)
		return __seq_set_%s_instance(v);

''' % self.bound_name

			if has_mutable_members:
				out += '''\
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
''' % (self.bound_name, self.bound_name)

			out += '''
	sq_pushnull(v);
	return sq_throwobject(v);
}\n\n'''

		out += 'static void delete_%s(void *o) { delete (%s *)o; }\n\n' % (self.bound_name, self.ctype)

		if self._inline:
			out += '''static void delete_inline_%s(void *o) {
	using T = %s;
	((T*)o)->~T();
}\n\n''' % (self.bound_name, self.ctype)

		out += 'static std::map<HSQUIRRELVM, std::map<void *, HSQOBJECT>> __instance_cache_%s;\n\n' % self.bound_name

		out += '''static void release_cached_%s_instance(HSQUIRRELVM v, void *obj) {
	if (!obj)
		return;

	auto vm_cache = __instance_cache_%s.find(v);
	if (vm_cache == __instance_cache_%s.end())
		return;

	auto instance = vm_cache->second.find(obj);
	if (instance == vm_cache->second.end())
		return;

	sq_release(v, &instance->second);
	vm_cache->second.erase(instance);
	if (vm_cache->second.empty())
		__instance_cache_%s.erase(vm_cache);
}\n\n''' % (self.bound_name, self.bound_name, self.bound_name, self.bound_name)

		out += '''static bool push_cached_%s_instance(HSQUIRRELVM v, void *obj) {
	if (!obj)
		return false;

	auto vm_cache = __instance_cache_%s.find(v);
	if (vm_cache == __instance_cache_%s.end())
		return false;

	auto instance = vm_cache->second.find(obj);
	if (instance == vm_cache->second.end())
		return false;

	sq_pushobject(v, instance->second);
	if (SQ_FAILED(sq_getweakrefval(v, -1))) {
		sq_poptop(v);
		release_cached_%s_instance(v, obj);
		return false;
	}

	sq_remove(v, -2);
	if (sq_gettype(v, -1) == OT_NULL) {
		sq_poptop(v);
		release_cached_%s_instance(v, obj);
		return false;
	}

	return true;
}\n\n''' % (self.bound_name, self.bound_name, self.bound_name, self.bound_name, self.bound_name)

		out += '''static void cache_%s_instance(HSQUIRRELVM v, void *obj) {
	if (!obj)
		return;

	sq_weakref(v, -1);

	HSQOBJECT weakref;
	sq_resetobject(&weakref);
	sq_getstackobj(v, -1, &weakref);
	sq_addref(v, &weakref);
	sq_poptop(v);

	auto &vm_cache = __instance_cache_%s[v];
	auto instance = vm_cache.find(obj);
	if (instance != vm_cache.end()) {
		sq_release(v, &instance->second);
		instance->second = weakref;
	} else {
		vm_cache[obj] = weakref;
	}
}\n\n''' % (self.bound_name, self.bound_name)

		out += '''static void release_cached_%s_instances(HSQUIRRELVM v) {
	auto vm_cache = __instance_cache_%s.find(v);
	if (vm_cache == __instance_cache_%s.end())
		return;

	for (auto &instance : vm_cache->second)
		sq_release(v, &instance.second);

	__instance_cache_%s.erase(vm_cache);
}\n\n''' % (self.bound_name, self.bound_name, self.bound_name, self.bound_name)

		if len(comparison_ops) > 0:
			out += '''static SQInteger __cmp_%s_instance(HSQUIRRELVM v) {
''' % self.bound_name

			if '==' in comparison_ops:
				out += '''\
	SQInteger eq_rval_count = %s(v);
	if (eq_rval_count == SQ_ERROR)
		return SQ_ERROR;
	if (eq_rval_count != 1 || sq_gettype(v, -1) != OT_BOOL)
		return sq_throwerror(v, _SC("internal error: invalid comparison result for %s"));
	SQBool is_equal = SQFalse;
	sq_getbool(v, -1, &is_equal);
	sq_poptop(v);
	if (is_equal) {
		sq_pushinteger(v, 0);
		return 1;
	}
''' % (comparison_ops['==']['proxy_name'], _escape_sq_string(self.bound_name))

			if '<' in comparison_ops:
				out += '''\
	SQInteger lt_rval_count = %s(v);
	if (lt_rval_count == SQ_ERROR)
		return SQ_ERROR;
	if (lt_rval_count != 1 || sq_gettype(v, -1) != OT_BOOL)
		return sq_throwerror(v, _SC("internal error: invalid comparison result for %s"));
	SQBool is_less = SQFalse;
	sq_getbool(v, -1, &is_less);
	sq_poptop(v);
	if (is_less) {
		sq_pushinteger(v, -1);
		return 1;
	}
''' % (comparison_ops['<']['proxy_name'], _escape_sq_string(self.bound_name))

			if '>' in comparison_ops:
				out += '''\
	SQInteger gt_rval_count = %s(v);
	if (gt_rval_count == SQ_ERROR)
		return SQ_ERROR;
	if (gt_rval_count != 1 || sq_gettype(v, -1) != OT_BOOL)
		return sq_throwerror(v, _SC("internal error: invalid comparison result for %s"));
	SQBool is_greater = SQFalse;
	sq_getbool(v, -1, &is_greater);
	sq_poptop(v);
	if (is_greater) {
		sq_pushinteger(v, 1);
		return 1;
	}
''' % (comparison_ops['>']['proxy_name'], _escape_sq_string(self.bound_name))

			if '!=' in comparison_ops:
				out += '''\
	SQInteger ne_rval_count = %s(v);
	if (ne_rval_count == SQ_ERROR)
		return SQ_ERROR;
	if (ne_rval_count != 1 || sq_gettype(v, -1) != OT_BOOL)
		return sq_throwerror(v, _SC("internal error: invalid comparison result for %s"));
	SQBool is_not_equal = SQFalse;
	sq_getbool(v, -1, &is_not_equal);
	sq_poptop(v);
	sq_pushinteger(v, is_not_equal ? 1 : 0);
	return 1;
''' % (comparison_ops['!=']['proxy_name'], _escape_sq_string(self.bound_name))
			elif '==' in comparison_ops:
				out += '''\
	sq_pushinteger(v, 1);
	return 1;
'''
			else:
				out += '''\
	sq_pushinteger(v, 0);
	return 1;
'''

			out += '}\n\n'

		if has_default_deep_compare:
			out += '''static SQInteger __default_cmp_%s_instance(HSQUIRRELVM v) {
	auto w1 = cast_to_wrapped_Object_safe(v, 1);
	auto w2 = cast_to_wrapped_Object_safe(v, 2);

	if (!w1 || !w2 || w1->type_tag != w2->type_tag)
		return sq_throwerror(v, _SC("invalid comparison between %s instances"));

	if (*(%s *)w1->obj == *(%s *)w2->obj) {
		sq_pushinteger(v, 0);
		return 1;
	}

	sq_pushinteger(v, *(%s *)w1->obj < *(%s *)w2->obj ? -1 : 1);
	return 1;
}\n\n''' % (
				self.bound_name,
				_escape_sq_string(self.bound_name),
				self.ctype,
				self.ctype,
				self.ctype,
				self.ctype
			)

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
		init_wrapped_Object(self, v, %s, (void *)self->inline_obj);
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
	tmp->vm = nullptr;
	tmp->on_release_cache = nullptr;
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
	if (own == NonOwning && push_cached_%s_instance(v, obj))
		return 1;

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
	init_wrapped_Object(w, v, %s, obj);
	if (own == NonOwning) {
		w->on_release_cache = &release_cached_%s_instance;
		cache_%s_instance(v, obj);
	}
	if (own != NonOwning)
		%s
	sq_setreleasehook(v, -1, wrapped_Object_releasehook);

	sq_remove(v, -2);
	sq_remove(v, -2);
	sq_remove(v, -2);
	return 1;
}\n''' % (
			self.from_c_func,
			self.bound_name,
			_escape_sq_string(module_name),
			_escape_sq_string(module_name),
			_escape_sq_string(self.bound_name),
			_escape_sq_string(self.bound_name),
			_escape_sq_string(module_name),
			self.type_tag,
			_escape_sq_string(self.bound_name),
			copy_code,
			self.type_tag,
			self.bound_name,
			self.bound_name,
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

		if has_sequence or len(all_members) > 0:
			out += '\t// instance member lookup\n'
			out += '\tsq_pushstring(v, _SC("_get"), -1);\n'
			out += '\tsq_newclosure(v, __get_%s_instance, 0);\n' % self.bound_name
			out += '\tsq_setnativeclosurename(v, -1, _SC("_get"));\n'
			out += '\tif (SQ_FAILED(sq_newslot(v, class_idx, SQFalse))) {\n'
			out += '\t\tsq_settop(v, top);\n'
			out += '\t\treturn SQ_ERROR;\n'
			out += '\t}\n\n'

		if has_sequence or has_mutable_members:
			out += '\t// instance member assignation\n'
			out += '\tsq_pushstring(v, _SC("_set"), -1);\n'
			out += '\tsq_newclosure(v, __set_%s_instance, 0);\n' % self.bound_name
			out += '\tsq_setnativeclosurename(v, -1, _SC("_set"));\n'
			out += '\tif (SQ_FAILED(sq_newslot(v, class_idx, SQFalse))) {\n'
			out += '\t\tsq_settop(v, top);\n'
			out += '\t\treturn SQ_ERROR;\n'
			out += '\t}\n\n'

		if has_repr:
			out += '\t// string representation\n'
			out += '\tsq_pushstring(v, _SC("_tostring"), -1);\n'
			out += '\tsq_newclosure(v, __tostring_%s_instance, 0);\n' % self.bound_name
			out += '\tsq_setnativeclosurename(v, -1, _SC("_tostring"));\n'
			out += '\tif (SQ_FAILED(sq_newslot(v, class_idx, SQFalse))) {\n'
			out += '\t\tsq_settop(v, top);\n'
			out += '\t\treturn SQ_ERROR;\n'
			out += '\t}\n\n'

		if len(all_static_members) > 0:
			out += '\t// static data member accessors\n'
			for member in all_static_members:
				member_bound_name = _get_default_bound_name(str(member['name']))
				getter_bound_name = 'get_%s' % member_bound_name
				out += '\tsq_pushstring(v, _SC("%s"), -1);\n' % _escape_sq_string(getter_bound_name)
				out += '\tsq_newclosure(v, %s, 0);\n' % member['getter']
				out += '\tsq_setnativeclosurename(v, -1, _SC("%s"));\n' % _escape_sq_string(getter_bound_name)
				out += '\tif (SQ_FAILED(sq_newslot(v, class_idx, SQFalse))) {\n'
				out += '\t\tsq_settop(v, top);\n'
				out += '\t\treturn SQ_ERROR;\n'
				out += '\t}\n'

				if member['setter']:
					setter_bound_name = 'set_%s' % member_bound_name
					out += '\tsq_pushstring(v, _SC("%s"), -1);\n' % _escape_sq_string(setter_bound_name)
					out += '\tsq_newclosure(v, %s, 0);\n' % member['setter']
					out += '\tsq_setnativeclosurename(v, -1, _SC("%s"));\n' % _escape_sq_string(setter_bound_name)
					out += '\tif (SQ_FAILED(sq_newslot(v, class_idx, SQFalse))) {\n'
					out += '\t\tsq_settop(v, top);\n'
					out += '\t\treturn SQ_ERROR;\n'
					out += '\t}\n'
			out += '\n'

		if has_sequence:
			out += '\t// sequence helpers\n'
			if not has_len_method:
				out += '\tsq_pushstring(v, _SC("len"), -1);\n'
				out += '\tsq_newclosure(v, __len_%s_instance, 0);\n' % self.bound_name
				out += '\tsq_setnativeclosurename(v, -1, _SC("len"));\n'
				out += '\tif (SQ_FAILED(sq_newslot(v, class_idx, SQFalse))) {\n'
				out += '\t\tsq_settop(v, top);\n'
				out += '\t\treturn SQ_ERROR;\n'
				out += '\t}\n'
			out += '\tsq_pushstring(v, _SC("_nexti"), -1);\n'
			out += '\tsq_newclosure(v, __nexti_%s_instance, 0);\n' % self.bound_name
			out += '\tsq_setnativeclosurename(v, -1, _SC("_nexti"));\n'
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

		if len(self.arithmetic_ops) > 0:
			out += '\t// arithmetic metamethods\n'
			for arithmetic_op in self.arithmetic_ops:
				if arithmetic_op['op'] not in sq_arithmetic_metamethods:
					continue
				out += '\tsq_pushstring(v, _SC("%s"), -1);\n' % sq_arithmetic_metamethods[arithmetic_op['op']]
				out += '\tsq_newclosure(v, %s, 0);\n' % arithmetic_op['proxy_name']
				out += '\tsq_setnativeclosurename(v, -1, _SC("%s"));\n' % sq_arithmetic_metamethods[arithmetic_op['op']]
				out += '\tif (SQ_FAILED(sq_newslot(v, class_idx, SQFalse))) {\n'
				out += '\t\tsq_settop(v, top);\n'
				out += '\t\treturn SQ_ERROR;\n'
				out += '\t}\n'
			out += '\n'

		if len(comparison_ops) > 0 or has_default_deep_compare:
			out += '\t// comparison metamethods\n'
			out += '\tsq_pushstring(v, _SC("_cmp"), -1);\n'
			if len(comparison_ops) > 0:
				out += '\tsq_newclosure(v, __cmp_%s_instance, 0);\n' % self.bound_name
			else:
				out += '\tsq_newclosure(v, __default_cmp_%s_instance, 0);\n' % self.bound_name
			out += '\tsq_setnativeclosurename(v, -1, _SC("_cmp"));\n'
			out += '\tif (SQ_FAILED(sq_newslot(v, class_idx, SQFalse))) {\n'
			out += '\t\tsq_settop(v, top);\n'
			out += '\t\treturn SQ_ERROR;\n'
			out += '\t}\n\n'

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
	if (type == OT_INTEGER || type == OT_NULL)
		return true;
	if (auto w = cast_to_wrapped_Object_safe(v, idx))
		return _type_tag_can_cast(w->type_tag, %s);
	return false;
}\n''' % (self.check_func, self.type_tag)

		out += '''void %s(HSQUIRRELVM v, SQInteger idx, void *obj) {
	if (sq_gettype(v, idx) == OT_NULL) {
		*((%s*)obj) = nullptr;
		return;
	}

	if (sq_gettype(v, idx) == OT_INTEGER) {
		SQInteger p = 0;
		sq_getinteger(v, idx, &p);
		*((%s*)obj) = (%s)p;
	} else if (auto w = cast_to_wrapped_Object_unsafe(v, idx)) {
		*(void **)obj = _type_tag_cast(w->obj, w->type_tag, %s);
	}
}\n''' % (self.to_c_func, self.ctype, self.ctype, self.ctype, self.type_tag)

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
		self.add_include('memory', True)

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

	HSQUIRRELVM vm;
	void (*on_release_cache)(HSQUIRRELVM, void *);
	void (*on_delete)(void *);
} wrapped_Object;

static void init_wrapped_Object(wrapped_Object *o, HSQUIRRELVM vm, uint32_t type_tag, void *obj) {
	o->magic_u32 = 0x46414221;
	o->type_tag = type_tag;

	o->obj = obj;

	o->vm = vm;
	o->on_release_cache = nullptr;
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
	if (w && w->on_release_cache && w->vm && w->obj)
		w->on_release_cache(w->vm, w->obj);
	if (w && w->on_delete)
		w->on_delete(w->obj);
	return 0;
}

'''

		self._source += '''
struct SquirrelVMRef {
	HSQUIRRELVM vm{nullptr};
	bool alive{true};
};

static std::map<HSQUIRRELVM, std::shared_ptr<SquirrelVMRef>> __squirrel_vm_refs;

static std::shared_ptr<SquirrelVMRef> acquire_squirrel_vm_ref(HSQUIRRELVM v) {
	auto &vm_ref = __squirrel_vm_refs[v];
	if (!vm_ref) {
		vm_ref = std::make_shared<SquirrelVMRef>();
		vm_ref->vm = v;
	}
	return vm_ref;
}

static void release_squirrel_vm_ref(HSQUIRRELVM v) {
	auto vm_ref = __squirrel_vm_refs.find(v);
	if (vm_ref == __squirrel_vm_refs.end())
		return;

	vm_ref->second->alive = false;
	__squirrel_vm_refs.erase(vm_ref);
}

class SquirrelValueRef {
public:
	SquirrelValueRef(HSQUIRRELVM v, SQInteger idx) : vm_ref(acquire_squirrel_vm_ref(v)) {
		sq_resetobject(&value);
		sq_resetobject(&env);

		sq_getstackobj(vm_ref->vm, idx, &value);
		sq_addref(vm_ref->vm, &value);

		if (SQ_SUCCEEDED(sq_getclosureroot(vm_ref->vm, idx))) {
			sq_getstackobj(vm_ref->vm, -1, &env);
			sq_addref(vm_ref->vm, &env);
			sq_poptop(vm_ref->vm);
		} else {
			sq_pushroottable(vm_ref->vm);
			sq_getstackobj(vm_ref->vm, -1, &env);
			sq_addref(vm_ref->vm, &env);
			sq_poptop(vm_ref->vm);
		}
	}

	~SquirrelValueRef() {
		if (!vm_ref || !vm_ref->alive)
			return;
		sq_release(vm_ref->vm, &value);
		sq_release(vm_ref->vm, &env);
	}

	const HSQOBJECT &GetValue() const { return value; }
	const HSQOBJECT &GetEnv() const { return env; }

private:
	std::shared_ptr<SquirrelVMRef> vm_ref;
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
		if ctx == 'rbind_args' or len(rvals) <= 1:
			return ''

		return '''\
SQInteger packed_rval_count = rval_count;
SQInteger first_rval_idx = arg_count + 2;
sq_newarray(v, 0);
SQInteger packed_rvals_idx = sq_gettop(v);
for (SQInteger i = 0; i < packed_rval_count; ++i) {
	sq_push(v, first_rval_idx + i);
	if (SQ_FAILED(sq_arrayappend(v, packed_rvals_idx)))
		return SQ_ERROR;
}
for (SQInteger i = 0; i < packed_rval_count; ++i)
	sq_remove(v, arg_count + 2);
rval_count = 1;
'''

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
		if len(self._bound_variables) > 0:
			self.add_include('string', True)

		super().finalize()

		self.output_binding_api()

		create_module_func = gen.apply_api_prefix('create_%s' % self._name)
		bind_module_func = gen.apply_api_prefix('bind_%s' % self._name)
		release_module_func = gen.apply_api_prefix('release_%s' % self._name)
		classes_to_register = [type for type in self._bound_types if isinstance(type, SquirrelClassTypeConverter)]
		has_bound_variables = len(self._bound_variables) > 0

		self._header += '// create the module object and push it onto the stack\n'
		self._header += 'SQRESULT %s(HSQUIRRELVM v);\n' % create_module_func
		self._header += '// create the module object and register it into the interpreter root table\n'
		self._header += 'SQRESULT %s(HSQUIRRELVM v, const SQChar *symbol);\n' % bind_module_func
		self._header += '// release VM-bound references tracked by the binding before sq_close\n'
		self._header += 'void %s(HSQUIRRELVM v);\n\n' % release_module_func

		if not self.embedded:
			self._source += '''\
#if WIN32
 #define _DLL_EXPORT_ __declspec(dllexport)
#else
 #define _DLL_EXPORT_
#endif
\n'''

		if has_bound_variables:
			self._source += build_index_map('__get_%s_var_map' % self._name, self._bound_variables, lambda v: True, lambda v: '\t{_SC("%s"), %s}' % (_escape_sq_string(v['bound_name']), v['getter']))
			self._source += build_index_map('__set_%s_var_map' % self._name, self._bound_variables, lambda v: v['setter'], lambda v: '\t{_SC("%s"), %s}' % (_escape_sq_string(v['bound_name']), v['setter']))

			self._source += '''static SQInteger __get_%s_var(HSQUIRRELVM v) {
	if (sq_gettype(v, 2) == OT_STRING) {
		const SQChar *key_cstr = nullptr;
		sq_getstring(v, 2, &key_cstr);
		std::basic_string<SQChar> key = key_cstr;

		auto i = __get_%s_var_map.find(key);
		if (i != __get_%s_var_map.end()) {
			sq_remove(v, 2);
			return i->second(v);
		}
	}

	sq_pushnull(v);
	return sq_throwobject(v);
}\n\n''' % (self._name, self._name, self._name)

			self._source += '''static SQInteger __set_%s_var(HSQUIRRELVM v) {
	if (sq_gettype(v, 2) == OT_STRING) {
		const SQChar *key_cstr = nullptr;
		sq_getstring(v, 2, &key_cstr);
		std::basic_string<SQChar> key = key_cstr;

		auto i = __set_%s_var_map.find(key);
		if (i != __set_%s_var_map.end()) {
			sq_remove(v, 2);
			return i->second(v);
		}
	}

	sq_pushnull(v);
	return sq_throwobject(v);
}\n\n''' % (self._name, self._name, self._name)

		self._source += 'SQRESULT %s(HSQUIRRELVM v) {\n' % create_module_func
		self._source += '\t__initialize_type_tag_infos();\n'
		self._source += '\t__initialize_type_infos();\n\n'
		self._source += '\t// custom initialization code\n'
		self._source += self._custom_init_code
		self._source += '\n'
		self._source += '\tsq_newtable(v);\n'
		if has_bound_variables or len(classes_to_register) > 0:
			self._source += '\tSQInteger module_idx = sq_gettop(v);\n'
		self._source += '\n'

		if has_bound_variables:
			self._source += '\t// bind variable lookup delegate\n'
			self._source += '\tsq_newtable(v);\n'
			self._source += '\tsq_pushstring(v, _SC("_get"), -1);\n'
			self._source += '\tsq_newclosure(v, __get_%s_var, 0);\n' % self._name
			self._source += '\tsq_setnativeclosurename(v, -1, _SC("_get"));\n'
			self._source += '\tif (SQ_FAILED(sq_newslot(v, -3, SQFalse)))\n'
			self._source += '\t\treturn SQ_ERROR;\n'
			self._source += '\tsq_pushstring(v, _SC("_set"), -1);\n'
			self._source += '\tsq_newclosure(v, __set_%s_var, 0);\n' % self._name
			self._source += '\tsq_setnativeclosurename(v, -1, _SC("_set"));\n'
			self._source += '\tif (SQ_FAILED(sq_newslot(v, -3, SQFalse)))\n'
			self._source += '\t\treturn SQ_ERROR;\n'
			self._source += '\tif (SQ_FAILED(sq_setdelegate(v, module_idx)))\n'
			self._source += '\t\treturn SQ_ERROR;\n\n'

		if len(classes_to_register) > 0:
			self._source += '\t// register bound classes\n'
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

		self._source += 'void %s(HSQUIRRELVM v) {\n' % release_module_func
		if self._custom_free_code:
			self._source += '\t// custom cleanup code\n'
			self._source += self._custom_free_code
			if not self._custom_free_code.endswith('\n'):
				self._source += '\n'
		for type in classes_to_register:
			self._source += '\trelease_cached_%s_instances(v);\n' % type.bound_name
		self._source += '\trelease_squirrel_vm_ref(v);\n'
		self._source += '}\n\n'

		if not self.embedded:
			self._source += 'extern "C" _DLL_EXPORT_ SQRESULT sqmodule_%s(HSQUIRRELVM v) {\n' % self._name
			self._source += '\treturn %s(v);\n' % create_module_func
			self._source += '}\n'
