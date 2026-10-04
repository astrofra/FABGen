"""QuickJS strings, copying arrays and std::function bridges."""
from lang.quickjs import QuickJSTypeConverterCommon, quote


class QuickJSStringConverter(QuickJSTypeConverterCommon):
    def get_type_glue(self, gen, module_name):
        return f'''
bool {self.check_func}(JSContext *, JSValueConst value) {{ return JS_IsString(value); }}
void {self.to_c_func}(JSContext *ctx, JSValueConst value, void *out) {{
    if (!JS_IsString(value)) qjs::type_error(ctx, "expected string");
    qjs::CString text(ctx, value);
    static_cast<std::string *>(out)->assign(text.data, text.size);
}}
JSValue {self.from_c_func}(JSContext *ctx, void *object, OwnershipPolicy) {{
    auto &text = *static_cast<std::string *>(object);
    return JS_NewStringLen(ctx, text.data(), text.size());
}}
'''


def bind_stl(gen):
    gen.add_include('string', True)
    gen.add_include('vector', True)
    gen.bind_type(QuickJSStringConverter('std::string'))


class QuickJSArrayToStdVectorConverter(QuickJSTypeConverterCommon):
    def __init__(self, type, T_conv):
        native = 'std::vector<%s>' % T_conv.ctype
        if T_conv.c_storage_class:
            raise ValueError('QuickJS: array of %s would retain temporary conversion storage; use std::string or owned values' % T_conv.ctype)
        super().__init__(type, native, from_c_storage_type=native)
        self.T_conv = T_conv
        self.overload_priority = getattr(T_conv, 'overload_priority', 0)

    def get_type_glue(self, gen, module_name):
        elem = self.T_conv
        cpp = 'std::vector<%s>' % elem.ctype
        element_check = elem.check_call('item')
        if elem.ctype.is_pointer():
            element_check = '(JS_IsNull(item) || %s)' % element_check
        out = f'''
bool {self.check_func}(JSContext *ctx, JSValueConst value) {{
    if (!qjs::is_array(ctx, value)) return false;
    uint32_t count = qjs::array_length(ctx, value);
    for (uint32_t i = 0; i < count; ++i) {{
        qjs::Value item(ctx, qjs::array_element(ctx, value, i));
        if (!{element_check}) return false;
    }}
    return true;
}}
void {self.to_c_func}(JSContext *ctx, JSValueConst value, void *out) {{
    if (!qjs::is_array(ctx, value)) qjs::type_error(ctx, "expected ordinary Array");
    uint32_t count = qjs::array_length(ctx, value);
    {cpp} converted;
    converted.reserve(count);
    for (uint32_t i = 0; i < count; ++i) {{
        qjs::Value item(ctx, qjs::array_element(ctx, value, i));
        if (!{element_check}) qjs::type_error(ctx, "invalid array element type");
        {elem.to_c_storage_ctype} native_item{{}};
        {elem.to_c_call('item', '&native_item')}
        converted.push_back({elem.prepare_var_from_conv('native_item', elem.ctype.get_ref())});
    }}
    *static_cast<{cpp} *>(out) = std::move(converted);
}}
JSValue {self.from_c_func}(JSContext *ctx, void *object, OwnershipPolicy) {{
    auto &values = *static_cast<{cpp} *>(object);
    qjs::Value array(ctx, qjs::checked(JS_NewArray(ctx)));
    if (values.size() > UINT32_MAX) qjs::range_error(ctx, "array is too large");
    for (uint32_t i = 0; i < values.size(); ++i) {{
        {elem.ctype} item = values[i];
        qjs::Value converted(ctx);
        {elem.from_c_call('converted', elem.prepare_var_for_conv('item', elem.ctype.get_ref()) if elem.is_type_class() else '&item', 'Copy')}
        qjs::check(JS_SetPropertyUint32(ctx, array, i, converted.release()));
    }}
    return array.release();
}}
'''
        return out


class QuickJSObjectToStdMapConverter(QuickJSTypeConverterCommon):
    """Own enumerable string data properties, copied to std::map<string, T>."""
    def __init__(self, type, K_conv, V_conv):
        if str(K_conv.ctype) != 'std::string' or V_conv.c_storage_class:
            raise ValueError('QuickJS: object maps require std::string keys and owned value conversions: ' + type)
        super().__init__(type)
        self.K_conv, self.V_conv = K_conv, V_conv

    def get_type_glue(self, gen, module_name):
        gen.add_include('map', True)
        conv = self.V_conv
        return f'''
bool {self.check_func}(JSContext *ctx, JSValueConst value) {{
    return qjs::is_record(ctx, value);
}}
void {self.to_c_func}(JSContext *ctx, JSValueConst value, void *out) {{
    if (!{self.check_func}(ctx, value)) qjs::type_error(ctx, "expected string-keyed object");
    qjs::OwnProperties keys(ctx, value);
    {self.ctype} converted;
    for (uint32_t i = 0; i < keys.count; ++i) {{
        JSPropertyDescriptor desc = {{}};
        int found = JS_GetOwnProperty(ctx, &desc, value, keys.names[i].atom);
        qjs::check(found);
        if (!found) qjs::type_error(ctx, "map property disappeared during conversion");
        qjs::Value getter(ctx, desc.getter), setter(ctx, desc.setter), item(ctx, desc.value);
        if ((desc.flags & JS_PROP_TMASK) == JS_PROP_GETSET) qjs::type_error(ctx, "map accessors are not accepted");
        qjs::Value key(ctx, qjs::checked(JS_AtomToString(ctx, keys.names[i].atom)));
        qjs::CString name(ctx, key);
        if (!{conv.check_call('item')}) qjs::type_error(ctx, "invalid map value type");
        {conv.to_c_storage_ctype} native_value{{}};
        {conv.to_c_call('item', '&native_value')}
        converted.emplace(std::string(name.data, name.size), {conv.prepare_var_from_conv('native_value', conv.ctype.get_ref())});
    }}
    *static_cast<{self.ctype} *>(out) = std::move(converted);
}}
JSValue {self.from_c_func}(JSContext *ctx, void *object, OwnershipPolicy) {{
    auto &values = *static_cast<{self.ctype} *>(object);
    qjs::Value result(ctx, qjs::checked(JS_NewObjectProto(ctx, JS_NULL)));
    for (const auto &entry : values) {{
        {conv.ctype} item = entry.second;
        qjs::Value converted(ctx);
        {conv.from_c_call('converted', conv.prepare_var_for_conv('item', conv.ctype.get_ref()) if conv.is_type_class() else '&item', 'Copy')}
        JSAtom key = JS_NewAtomLen(ctx, entry.first.data(), entry.first.size());
        if (key == JS_ATOM_NULL) throw qjs::PendingException();
        int status = JS_DefinePropertyValue(ctx, result, key, converted.release(), JS_PROP_C_W_E);
        JS_FreeAtom(ctx, key);
        qjs::check(status);
    }}
    return result.release();
}}
'''


def bind_function_T(gen, type, bound_name=None):
    class QuickJSStdFunctionConverter(QuickJSTypeConverterCommon):
        def get_type_glue(self, gen, module_name):
            function = self.ctype.scoped_typename.parts[-1].template.function
            rval = 'void' if hasattr(function, 'void_rval') else str(function.rval)
            args = [str(arg) for arg in function.args] if hasattr(function, 'args') else []
            parms = ['%s v%d' % (arg, i) for i, arg in enumerate(args)]
            helper = '_rbind_' + self.bound_name
            gen.rbind_function(helper, rval, parms, True)
            gen._bind_proxy('invoke_' + self.bound_name, self, [(rval, parms, [])],
                            'native callback ' + self.bound_name,
                            lambda args: '_self(%s);' % ', '.join(args), 'method')
            native_call = '%s(ctx, ref->function, JS_UNDEFINED%s)' % (
                gen.apply_api_prefix(helper), ''.join(', v%d' % i for i in range(len(args))))
            return f'''
bool {self.check_func}(JSContext *ctx, JSValueConst value) {{
    return JS_IsFunction(ctx, value) || qjs::is_native(value, {self.type_tag});
}}
void {self.to_c_func}(JSContext *ctx, JSValueConst value, void *out) {{
    if (qjs::is_native(value, {self.type_tag})) {{
        *static_cast<{self.ctype} *>(out) = *static_cast<{self.ctype} *>(qjs::unwrap(ctx, value, {self.type_tag}));
        return;
    }}
    if (!JS_IsFunction(ctx, value)) qjs::type_error(ctx, "expected callable");
    auto ref = qjs::retain_callback(ctx, value);
    *static_cast<{self.ctype} *>(out) = [ref]({', '.join(parms)}) -> {rval} {{
        ref->require_live();
        JSContext *ctx = ref->ctx;
        {'return ' if rval != 'void' else ''}{native_call};
    }};
}}
static JSValue thunk_{self.bound_name}(JSContext *ctx, JSValueConst, int argc, JSValueConst *argv, int, JSValue *data) {{
    return invoke_{self.bound_name}(ctx, data[0], argc, argv);
}}
JSValue {self.from_c_func}(JSContext *ctx, void *object, OwnershipPolicy) {{
    auto &fn = *static_cast<{self.ctype} *>(object);
    if (!fn) return JS_NULL;
    auto *copy = new {self.ctype}(fn);
    qjs::Value holder(ctx, qjs::wrap(ctx, {quote(self.ctype)}, qjs::make_native({self.type_tag}, copy,
        qjs::destroy<{self.ctype}>, _type_tag_can_cast, _type_tag_cast), false));
    JSValue data[] = {{holder}};
    return JS_NewCFunctionData(ctx, thunk_{self.bound_name}, {len(args)}, 0, 1, data);
}}
'''
    return gen.bind_type(QuickJSStdFunctionConverter(type, bound_name=bound_name))
