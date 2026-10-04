"""Official QuickJS backend. Standard ECMAScript, without operator extensions."""
import json
import zlib
from pathlib import Path

import gen


def quote(value):
    return json.dumps(str(value), ensure_ascii=True)


OPERATORS = {
    '+': 'add', '-': 'sub', '*': 'mul', '/': 'div',
    '+=': 'addAssign', '-=': 'subAssign', '*=': 'mulAssign', '/=': 'divAssign',
    '==': 'equals', '!=': 'notEquals', '<': 'lessThan', '<=': 'lessEqual',
    '>': 'greaterThan', '>=': 'greaterEqual',
}


class QuickJSTypeConverterCommon(gen.TypeConverter):
    def get_type_api(self, module_name):
        storage = ', %s &storage' % self.c_storage_class if self.c_storage_class else ''
        return (('struct %s;\n' % self.c_storage_class if self.c_storage_class else '') +
                'bool %s(JSContext *ctx, JSValueConst value);\n' % self.check_func +
                'void %s(JSContext *ctx, JSValueConst value, void *out%s);\n' % (self.to_c_func, storage) +
                'JSValue %s(JSContext *ctx, void *object, OwnershipPolicy policy);\n' % self.from_c_func)

    def to_c_call(self, in_var, out_var_p):
        if self.c_storage_class:
            storage = 'storage_' + gen.get_clean_symbol_name(out_var_p)
            return '%s %s;\n%s(ctx, %s, %s, %s);\n' % (self.c_storage_class, storage, self.to_c_func, in_var, out_var_p, storage)
        return '%s(ctx, %s, %s);\n' % (self.to_c_func, in_var, out_var_p)

    def from_c_call(self, out_var, expr, ownership):
        # One statement: rval_transform delegates may use unbraced if/else.
        return '%s = qjs::checked(%s(ctx, (void *)%s, %s));\n' % (out_var, self.from_c_func, expr, ownership)

    def check_call(self, in_var):
        return '%s(ctx, %s)' % (self.check_func, in_var)


class QuickJSClassTypeConverter(QuickJSTypeConverterCommon):
    def is_type_class(self):
        return True

    def get_type_glue(self, generator, module_name):
        name = self.bound_name
        cpp = str(self.ctype)
        unknown = set(self._features) - {'proxy', 'sequence', 'repr', 'rval_transform'}
        if unknown:
            raise ValueError('QuickJS: %s has unsupported type features: %s' % (cpp, ', '.join(sorted(unknown))))
        if self._non_copyable:
            copy = ('new %s(std::move(*static_cast<%s *>(object)))' % (cpp, cpp)) if self._moveable else None
        else:
            copy = 'new %s(*static_cast<%s *>(object))' % (cpp, cpp)
        out = '''
bool %(check)s(JSContext *, JSValueConst value) { return qjs::is_native(value, %(tag)s); }
void %(to)s(JSContext *ctx, JSValueConst value, void *out) {
    *static_cast<%(cpp)s **>(out) = static_cast<%(cpp)s *>(qjs::unwrap(ctx, value, %(tag)s));
}
JSValue %(from)s(JSContext *ctx, void *object, OwnershipPolicy policy) {
    if (!object) return JS_NULL;
''' % dict(check=self.check_func, tag=self.type_tag, to=self.to_c_func, cpp=cpp, **{'from': self.from_c_func})
        if copy:
            out += '    if (policy == Copy) object = %s;\n' % copy
        else:
            out += '    if (policy == Copy) qjs::type_error(ctx, %s);\n' % quote('cannot copy noncopyable ' + cpp)
        out += '''    return qjs::wrap(ctx, %(name)s, qjs::make_native(%(tag)s, object,
        policy == NonOwning ? nullptr : qjs::destroy<%(cpp)s>, _type_tag_can_cast, _type_tag_cast), policy == NonOwning);
}
''' % dict(name=quote(cpp), tag=self.type_tag, cpp=cpp)

        methods = [(str(m['bound_name']), m['proxy_name']) for m in self.get_all_methods()]
        existing = {n for n, _ in methods} | {str(m['name']) for m in self.get_all_members()}
        for op in self.arithmetic_ops + self.comparison_ops:
            mapped = OPERATORS[op['op']]
            if mapped in existing:
                raise ValueError('QuickJS: %s operator %s collides with member %s' % (cpp, op['op'], mapped))
            methods.append((mapped, op['proxy_name']))
            existing.add(mapped)

        if not any(op['op'] == '==' for op in self.comparison_ops) and 'equals' not in existing:
            # Without declared value equality, compare native addresses (including
            # shared_ptr's pointee), separately from JavaScript wrapper identity.
            body = generator._prepare_to_c_self(self, '_self')
            body += 'if (arg_count != 1 || !%s) return JS_FALSE;\n' % self.check_call('argv[0]')
            body += generator.prepare_to_c_var(0, self, 'other')
            compare = '*_self == *other' if self._supports_deep_compare else '_self == other'
            out += generator.open_proxy('equal_' + name, 1, 'method') + body
            out += 'return JS_NewBool(ctx, %s);\n' % compare + generator.close_proxy('method')
            methods.append(('equals', 'equal_' + name))

        if 'repr' in self._features:
            if 'toString' in existing:
                raise ValueError('QuickJS: repr collides with %s.toString' % cpp)
            out += generator.open_proxy('repr_' + name, 0, 'method')
            out += generator._prepare_to_c_self(self, '_self') + 'std::string repr;\n'
            out += self._features['repr']('_self', 'repr')
            out += 'return JS_NewStringLen(ctx, repr.data(), repr.size());\n' + generator.close_proxy('method')
            methods.append(('toString', 'repr_' + name))

        if 'sequence' in self._features:
            seq = self._features['sequence']
            for method in ('get', 'set', 'length'):
                if method in existing:
                    raise ValueError('QuickJS: sequence member %s.%s collides with a declaration' % (cpp, method))
            out += generator.open_proxy('length_' + name, 0, 'getter')
            out += generator._prepare_to_c_self(self, '_self') + 'size_t size = 0;\n'
            out += seq.get_size('_self', 'size')
            out += 'return JS_NewFloat64(ctx, double(size));\n' + generator.close_proxy('getter')
            for action, argc in [('get', 1), ('set', 2)]:
                out += generator.open_proxy(action + '_' + name, argc, 'method')
                out += 'if (arg_count != %d) qjs::type_error(ctx, "invalid sequence argument count");\n' % argc
                out += generator._prepare_to_c_self(self, '_self')
                out += generator.prepare_to_c_var(0, generator.get_conv('int'), 'index')
                out += 'bool error = false;\n'
                if action == 'get':
                    out += generator.decl_var(seq.wrapped_conv.ctype, 'rval', '{};\n')
                    out += seq.get_item('_self', 'index', 'rval', 'error')
                else:
                    out += generator.prepare_to_c_var(1, seq.wrapped_conv, 'item')
                    out += seq.set_item('_self', 'index', 'item', 'error')
                out += 'if (error) qjs::range_error(ctx, "sequence index out of range");\n'
                if action == 'get':
                    out += generator.prepare_from_c_var(dict(conv=seq.wrapped_conv, ctype=seq.wrapped_conv.ctype, var='rval', is_arg_in_out=False, ownership='Copy'))
                    out += generator.commit_from_c_vars(['rval'])
                out += generator.close_proxy('method')
                methods.append((action, action + '_' + name))

        ctor = self.constructor['proxy_name'] if self.constructor else 'no_construct_' + name
        if not self.constructor:
            out += generator.open_proxy(ctor, 0, 'constructor')
            out += generator.set_error('type', cpp + ' has no bound constructor') + generator.close_proxy('constructor')
        out += '''static JSValue register_%s(JSContext *ctx) {
    qjs::Value registry(ctx, qjs::registry(ctx));
    qjs::Value existing(ctx, qjs::checked(JS_GetPropertyStr(ctx, registry, %s)));
    if (JS_IsObject(existing)) return qjs::checked(JS_GetPropertyStr(ctx, existing, "constructor"));
    qjs::Value proto(ctx, qjs::checked(JS_NewObject(ctx)));
''' % (name, quote(cpp))
        if self._bases:
            base = self._bases[0]
            out += '    qjs::Value base_ctor(ctx, register_%s(ctx));\n' % base.bound_name
            out += '    qjs::Value base_proto(ctx, qjs::checked(JS_GetPropertyStr(ctx, base_ctor, "prototype")));\n'
            out += '    qjs::check(JS_SetPrototype(ctx, proto, base_proto));\n'
        for method, proxy in methods:
            out += '    qjs::method(ctx, proto, %s, %s, 0);\n' % (quote(method), proxy)
        for member in self.get_all_members():
            out += '    qjs::accessor(ctx, proto, %s, %s, %s);\n' % (quote(member['name']), member['getter'], member['setter'] or 'nullptr')
        if 'sequence' in self._features:
            out += '    qjs::accessor(ctx, proto, "length", length_%s, nullptr);\n' % name
        out += '    qjs::Value ctor(ctx, qjs::checked(JS_NewCFunction2(ctx, %s, %s, 0, JS_CFUNC_constructor, 0)));\n' % (ctor, quote(name))
        out += '    JS_SetConstructor(ctx, ctor, proto);\n'
        for method in self.get_all_static_methods():
            out += '    qjs::method(ctx, ctor, %s, %s, 0);\n' % (quote(method['bound_name']), method['proxy_name'])
        for member in self.get_all_static_members():
            out += '    qjs::accessor(ctx, ctor, %s, %s, %s);\n' % (quote(member['name']), member['getter'], member['setter'] or 'nullptr')
        out += '    qjs::property(ctx, registry, %s, proto.release());\n    return ctor.release();\n}\n' % quote(cpp)
        return out


class QuickJSPtrTypeConverter(QuickJSTypeConverterCommon):
    def get_type_glue(self, generator, module_name):
        return '''
bool %(check)s(JSContext *, JSValueConst value) { return qjs::is_native(value, %(tag)s); }
void %(to)s(JSContext *ctx, JSValueConst value, void *out) {
    *static_cast<%(cpp)s *>(out) = static_cast<%(cpp)s>(qjs::unwrap(ctx, value, %(tag)s));
}
JSValue %(from)s(JSContext *ctx, void *object, OwnershipPolicy policy) {
    if (policy == Owning) qjs::type_error(ctx, "opaque pointers require an explicit owning class converter");
    void *pointer = (void *)*static_cast<%(cpp)s *>(object);
    if (!pointer) return JS_NULL;
    return qjs::wrap(ctx, %(name)s, qjs::make_native(%(tag)s, pointer, nullptr, _type_tag_can_cast, _type_tag_cast), true);
}
''' % dict(check=self.check_func, to=self.to_c_func, cpp=self.ctype, tag=self.type_tag, name=quote(self.ctype), **{'from': self.from_c_func})


class QuickJSExternTypeConverter(QuickJSTypeConverterCommon):
    def __init__(self, type, to_c_storage_type, bound_name, module):
        super().__init__(type, to_c_storage_type, bound_name)
        self.module = module

    def get_type_api(self, module_name):
        return ('extern bool (*%s)(JSContext *, JSValueConst);\n' % self.check_func +
                'extern void (*%s)(JSContext *, JSValueConst, void *);\n' % self.to_c_func +
                'extern JSValue (*%s)(JSContext *, void *, OwnershipPolicy);\n' % self.from_c_func)

    def check_call(self, in_var):
        return '(%s && %s(ctx, %s))' % (self.check_func, self.check_func, in_var)

    def to_c_call(self, in_var, out_var_p):
        return 'if (!%s) qjs::type_error(ctx, %s);\n' % (self.to_c_func, quote('unlinked external type ' + str(self.ctype))) + super().to_c_call(in_var, out_var_p)

    def from_c_call(self, out_var, expr, ownership):
        return '%s = qjs::checked(%s ? %s(ctx, (void *)%s, %s) : JS_ThrowTypeError(ctx, %s));\n' % (out_var, self.from_c_func, self.from_c_func, expr, ownership, quote('unlinked external type ' + str(self.ctype)))

    def get_type_glue(self, generator, module_name):
        return self.get_type_api(module_name).replace('extern ', '').replace(');', ') = nullptr;')


class QuickJSGenerator(gen.FABGen):
    default_class_converter = QuickJSClassTypeConverter
    default_ptr_converter = QuickJSPtrTypeConverter
    default_extern_converter = QuickJSExternTypeConverter

    def get_language(self):
        return 'QuickJS'

    def begin_type(self, conv, features, nobind=False):
        if not isinstance(conv, QuickJSTypeConverterCommon):
            raise ValueError('QuickJS: %s uses incompatible converter %s; implement a QuickJSTypeConverterCommon adapter' % (conv.ctype, type(conv).__name__))
        start = len(self._source)
        result = super().begin_type(conv, features, nobind)
        # Native type identity is independent of a language-facing alias/prefix.
        old = hex(zlib.crc32(conv.bound_name.encode()) & 0xffffffff)
        new = hex(zlib.crc32(str(conv.ctype).encode()) & 0xffffffff)
        self._source = self._source[:start] + self._source[start:].replace('= %s;' % old, '= %s;' % new, 1)
        return result

    def start(self, module_name):
        super().start(module_name)
        self._source += '#include "fabgen_quickjs.h"\nnamespace qjs = fabgen_quickjs;\n'
        self._header += '#include <quickjs.h>\n'
        self._header += self.get_binding_api_declaration()
        self._source += self.get_binding_api_declaration()

    def get_binding_api_declaration(self):
        info = self.apply_api_prefix('type_info')
        return '''struct %s {
    uint32_t type_tag;
    const char *c_type;
    const char *bound_name;
    bool (*check)(JSContext *, JSValueConst);
    void (*to_c)(JSContext *, JSValueConst, void *);
    JSValue (*from_c)(JSContext *, void *, OwnershipPolicy);
};
%s *%s(uint32_t tag);
%s *%s(const char *name);
''' % (info, info, self.apply_api_prefix('get_bound_type_info'), info, self.apply_api_prefix('get_c_type_info'))

    def set_error(self, type, reason):
        return 'return JS_ThrowTypeError(ctx, "%%s", %s);\n' % quote(reason)

    def proxy_call_error(self, msg, ctx):
        return self.set_error('runtime', msg)

    def get_self(self, ctx):
        return 'this_val'

    def get_var(self, i, ctx):
        return '_js_result' if ctx == 'rbind_rval' else 'argv[%d]' % i

    def open_proxy(self, name, max_arg_count, ctx):
        return '''static JSValue %s(JSContext *ctx, JSValueConst this_val, int arg_count, JSValueConst *argv) {
    try {
        qjs::CallScope scope(ctx, this_val, arg_count, argv);
''' % name

    def close_proxy(self, ctx):
        return '''    return JS_UNDEFINED;
    } catch (const qjs::PendingException &) { return JS_EXCEPTION; }
      catch (const std::exception &e) { return JS_ThrowInternalError(ctx, "%s", e.what()); }
      catch (...) { return JS_ThrowInternalError(ctx, "unknown C++ exception"); }
}
'''

    def _prepare_to_c_self(self, conv, out_var, ctx='none', features=[]):
        return 'if (!%s) qjs::type_error(ctx, %s);\n' % (conv.check_call('this_val'), quote('invalid receiver for ' + str(conv.ctype))) + super()._prepare_to_c_self(conv, out_var, ctx, features)

    def _declare_to_c_var(self, ctype, var):
        return self.decl_var(ctype, var, '{};\n')

    def _bind_proxy(self, name, self_conv, protos, desc, expr_eval, ctx, fixed_arg_count=None):
        # Test complete signatures: unlike stack backends, Number overlaps int
        # and float. Integer candidates precede floating candidates, with full
        # backtracking if a later parameter does not match.
        try:
            prepared = self._build_protos(protos)
        except Exception as error:
            raise ValueError('QuickJS: %s: %s' % (desc, error)) from error

        supported = {'route', 'proxy', 'arg_out', 'arg_in_out', 'exception', 'new_obj', 'copy_obj',
                     'check_rval', 'validate_arg_in', 'bound_name', 'constants_group', 'rval_constants_group'}
        for proto in prepared:
            unknown = set(proto['features']) - supported
            if unknown:
                raise ValueError('QuickJS: %s has unsupported features: %s' % (desc, ', '.join(sorted(unknown))))

        def rank(proto):
            return sum(getattr(arg['conv'], 'overload_priority', 0) for arg in proto['argsin'])

        out = self.open_proxy(name, max(len(p['argsin']) for p in prepared), ctx)
        for proto in sorted(prepared, key=rank):
            checks = ['arg_count == %d' % len(proto['argsin'])]
            for i, arg in enumerate(proto['argsin']):
                conv = arg['conv']
                check = conv.check_call('argv[%d]' % i)
                if arg['carg'].ctype.get_ref() == '*' and isinstance(conv, (QuickJSClassTypeConverter, QuickJSPtrTypeConverter)):
                    check = '(JS_IsNull(argv[%d]) || %s)' % (i, check)
                checks.append(check)
            out += 'if (%s) {\n' % ' && '.join(checks)
            out += self._proto_call(self_conv, proto, expr_eval, ctx, fixed_arg_count)
            out += '}\n'
        signatures = '; '.join('%s(%s)' % (desc, ', '.join(str(a['carg'].ctype) for a in p['argsin'])) for p in prepared)
        out += self.set_error('type', 'no matching overload: ' + signatures)
        out += self.close_proxy(ctx)
        self._source += out

    def declare_from_c_var(self, out_var):
        return 'qjs::Value %s(ctx);\n' % out_var

    def rval_from_nullptr(self, out_var):
        return '%s = JS_NULL;\n' % out_var

    def rval_from_c_ptr(self, conv, out_var, expr, ownership):
        return conv.from_c_call(out_var, expr, ownership)

    def rval_assign_arg_in_out(self, out_var, arg_in_out):
        return '%s = JS_DupValue(ctx, %s);\n' % (out_var, arg_in_out)

    def return_void_from_c(self):
        return 'return JS_UNDEFINED;\n'

    def commit_from_c_vars(self, rvals, ctx='default'):
        names = [str(v) + '_out' for v in rvals]
        if ctx == 'rbind_args':
            return 'JSValue _js_args[] = {%s};\n' % (', '.join(names) if names else 'JS_UNDEFINED')
        if ctx == 'inplace_arithmetic_op':
            return 'return JS_DupValue(ctx, this_val);\n'
        if not names:
            return 'return JS_UNDEFINED;\n'
        if len(names) == 1:
            if ctx == 'constructor':
                return ('qjs::Value prototype(ctx, qjs::checked(JS_GetPropertyStr(ctx, this_val, "prototype")));\n'
                        'if (JS_IsObject(prototype)) qjs::check(JS_SetPrototype(ctx, %s, prototype));\n' % names[0] +
                        'return %s.release();\n' % names[0])
            return 'return %s.release();\n' % names[0]
        out = 'qjs::Value results(ctx, qjs::checked(JS_NewArray(ctx)));\n'
        for i, name in enumerate(names):
            out += 'qjs::check(JS_SetPropertyUint32(ctx, results, %d, %s.release()));\n' % (i, name)
        return out + 'return results.release();\n'

    def rbind_function(self, name, rval, args, internal=False):
        parsed = [self.parse_named_ctype(arg) for arg in args]
        result = None if rval == 'void' else self.select_ctype_conv(self.parse_ctype(rval))
        if result and (self.parse_ctype(rval).get_ref() or result.c_storage_class):
            raise ValueError('QuickJS: reverse binding %s cannot return a borrowed reference/pointer/storage value (%s); return an owned value' % (name, rval))
        if result and result._non_copyable:
            raise ValueError('QuickJS: reverse binding %s cannot copy a noncopyable callback result (%s)' % (name, rval))
        signature = '%s %s(JSContext *ctx, JSValueConst function, JSValueConst receiver%s, bool *success%s)' % (
            rval, self.apply_api_prefix(name), ''.join(', ' + str(arg) for arg in parsed), ' = nullptr' if internal else '')
        if not internal:
            self._header += signature[:-1] + ' = nullptr);\n'
        out = ('static ' if internal else '') + signature + ' {\nif (success) *success = false;\ntry {\n'
        for arg in parsed:
            conv = self.select_ctype_conv(arg.ctype)
            # JS callbacks can keep their arguments: value arguments must copy.
            out += self.prepare_from_c_var(dict(conv=conv, ctype=arg.ctype, var=arg.name, is_arg_in_out=False, ownership=None))
        out += self.commit_from_c_vars([a.name for a in parsed], 'rbind_args')
        out += 'qjs::Value _js_result(ctx, qjs::checked(JS_Call(ctx, function, receiver, %d, _js_args)));\n' % len(parsed)
        out += 'if (JS_PromiseState(ctx, _js_result) >= 0) qjs::type_error(ctx, "synchronous native callback returned a Promise");\n'
        if result:
            out += 'if (!%s) qjs::type_error(ctx, "incorrect callback result type");\n' % result.check_call('_js_result')
            out += self._declare_to_c_var(result.to_c_storage_ctype, 'native_result')
            out += result.to_c_call('_js_result', '&native_result')
            out += '%s result = %s;\n' % (rval, result.prepare_var_from_conv('native_result', ''))
        out += 'if (success) *success = true;\n'
        out += 'return result;\n' if result else 'return;\n'
        out += '''} catch (const qjs::PendingException &) {
    if (!success) throw;
} catch (const std::exception &e) {
    JS_ThrowInternalError(ctx, "%s", e.what());
    if (!success) throw qjs::PendingException();
} catch (...) {
    JS_ThrowInternalError(ctx, "C++ exception in reverse binding");
    if (!success) throw qjs::PendingException();
}
'''
        if result:
            out += 'return {};\n'
        self._source += out + '}\n'

    def finalize(self):
        super().finalize()
        info = self.apply_api_prefix('type_info')
        types = [t for t in self._bound_types if not t.c_storage_class]
        self._source += 'static %s type_infos[] = {\n' % info
        for conv in types:
            self._source += '{%s, %s, %s, %s, %s, %s},\n' % (conv.type_tag, quote(conv.ctype), quote(conv.bound_name), conv.check_func, conv.to_c_func, conv.from_c_func)
        self._source += '{0, nullptr, nullptr, nullptr, nullptr, nullptr}};\n'
        self._source += '%s *%s(uint32_t tag) { for (auto &info : type_infos) if (info.c_type && info.type_tag == tag) return &info; return nullptr; }\n' % (info, self.apply_api_prefix('get_bound_type_info'))
        self._source += '%s *%s(const char *name) { for (auto &info : type_infos) if (info.c_type && std::strcmp(info.c_type, name) == 0) return &info; return nullptr; }\n' % (info, self.apply_api_prefix('get_c_type_info'))

        create = self.apply_api_prefix('create_' + self._name)
        release = self.apply_api_prefix('release_' + self._name)
        init = self.apply_api_prefix('js_init_module_' + gen.get_clean_symbol_name(self._name))
        self._header += '''// Owned module object; caller must JS_FreeValue it.
JSValue %s(JSContext *ctx);
// Call before JS_FreeContext, after disconnecting native callbacks.
void %s(JSContext *ctx);
extern "C" JSModuleDef *%s(JSContext *ctx, const char *module_name);
''' % (create, release, init)
        exports = []

        def export(name):
            if name in exports:
                raise ValueError('QuickJS: duplicate export %s in %s' % (name, self._name))
            exports.append(name)

        out = 'JSValue %s(JSContext *ctx) {\ntry {\nqjs::Value module(ctx, qjs::checked(JS_NewObject(ctx)));\n' % create
        module_key = self.apply_api_prefix(self._name)
        out += 'if (qjs::begin_module(ctx, %s)) {\n%s\n}\n' % (quote(module_key), self._custom_init_code)
        for conv in self._bound_types:
            if isinstance(conv, QuickJSClassTypeConverter):
                if not conv.nobind:
                    export(str(conv.bound_name))
                    out += 'qjs::property(ctx, module, %s, register_%s(ctx));\n' % (quote(conv.bound_name), conv.bound_name)
                else:
                    out += '{ qjs::Value hidden(ctx, register_%s(ctx)); }\n' % conv.bound_name
        for fn in self._bound_functions:
            export(str(fn['bound_name']))
            out += 'qjs::method(ctx, module, %s, %s, 0);\n' % (quote(fn['bound_name']), fn['proxy_name'])
        for enum in self._enums.values():
            for name, value in enum.items():
                export(name)
                out += 'qjs::property(ctx, module, %s, qjs::new_integer(ctx, static_cast<typename std::underlying_type<decltype(%s)>::type>(%s)));\n' % (quote(name), value, value)
        for var in self._bound_variables:
            export(str(var['bound_name']))
            out += 'qjs::accessor(ctx, module, %s, %s, %s);\n' % (quote(var['bound_name']), var['getter'], var['setter'] or 'nullptr')
            if var['setter']:
                # ES module namespace properties cannot be C++ accessors. Named
                # getters/setters and the default module object stay live.
                for stem, proxy in [('get_', var['getter']), ('set_', var['setter'])]:
                    name = stem + str(var['bound_name'])
                    export(name)
                    out += 'qjs::method(ctx, module, %s, %s, 0);\n' % (quote(name), proxy)
        out += 'return module.release();\n} catch (const qjs::PendingException &) { return JS_EXCEPTION; }\ncatch (const std::exception &e) { return JS_ThrowInternalError(ctx, "%s", e.what()); }\ncatch (...) { return JS_ThrowInternalError(ctx, "C++ exception during module creation"); }\n}\n'
        out += 'void %s(JSContext *ctx) {\nif (qjs::end_module(ctx, %s)) {\n%s\n}\nqjs::release_context(ctx);\n}\n' % (release, quote(module_key), self._custom_free_code)
        export('default')
        out += 'static int initialize_module(JSContext *ctx, JSModuleDef *module) {\ntry {\nqjs::Value object(ctx, qjs::checked(%s(ctx)));\n' % create
        for name in exports[:-1]:
            out += 'qjs::check(JS_SetModuleExport(ctx, module, %s, qjs::checked(JS_GetPropertyStr(ctx, object, %s))));\n' % (quote(name), quote(name))
        out += 'qjs::check(JS_SetModuleExport(ctx, module, "default", object.release()));\nreturn 0;\n} catch (const qjs::PendingException &) { return -1; }\ncatch (const std::exception &e) { JS_ThrowInternalError(ctx, "%s", e.what()); return -1; }\ncatch (...) { JS_ThrowInternalError(ctx, "module initialization failed"); return -1; }\n}\n'
        out += 'extern "C" JSModuleDef *%s(JSContext *ctx, const char *name) {\nJSModuleDef *module = JS_NewCModule(ctx, name, initialize_module);\nif (!module) return nullptr;\n' % init
        for name in exports:
            out += 'if (JS_AddModuleExport(ctx, module, %s) < 0) return nullptr;\n' % quote(name)
        out += 'return module;\n}\n'
        if not self.embedded:
            self._header += '#ifdef FABGEN_QUICKJS_DYNAMIC_MODULE\nextern "C" JSModuleDef *js_init_module(JSContext *, const char *);\n#endif\n'
            out += '#ifdef FABGEN_QUICKJS_DYNAMIC_MODULE\nextern "C" JSModuleDef *js_init_module(JSContext *ctx, const char *name) { return %s(ctx, name); }\n#endif\n' % init
        self._source += out

    def get_output(self):
        output = super().get_output()
        output['fabgen_quickjs.h'] = (Path(__file__).resolve().parent.parent / 'lib' / 'quickjs' / 'runtime.h').read_text(encoding='utf-8')
        return output
