"""Strict primitive conversions; no ToNumber/ToString coercion of objects."""
from lang.quickjs import QuickJSTypeConverterCommon


class QuickJSBoolConverter(QuickJSTypeConverterCommon):
    def get_type_glue(self, gen, module_name):
        return f'''
bool {self.check_func}(JSContext *, JSValueConst value) {{ return JS_IsBool(value); }}
void {self.to_c_func}(JSContext *ctx, JSValueConst value, void *out) {{
    if (!JS_IsBool(value)) qjs::type_error(ctx, "expected boolean");
    *static_cast<bool *>(out) = JS_ToBool(ctx, value) != 0;
}}
JSValue {self.from_c_func}(JSContext *ctx, void *object, OwnershipPolicy) {{
    return JS_NewBool(ctx, *static_cast<bool *>(object));
}}
'''


class QuickJSIntConverter(QuickJSTypeConverterCommon):
    overload_priority = 0

    def get_type_glue(self, gen, module_name):
        return f'''
bool {self.check_func}(JSContext *ctx, JSValueConst value) {{ return qjs::integer<{self.ctype}>(ctx, value); }}
void {self.to_c_func}(JSContext *ctx, JSValueConst value, void *out) {{
    if (!qjs::integer(ctx, value, static_cast<{self.ctype} *>(out)))
        qjs::type_error(ctx, "expected an exact, in-range {self.ctype}");
}}
JSValue {self.from_c_func}(JSContext *ctx, void *object, OwnershipPolicy) {{
    return qjs::new_integer(ctx, *static_cast<{self.ctype} *>(object));
}}
'''


class QuickJSFloatConverter(QuickJSTypeConverterCommon):
    overload_priority = 10

    def get_type_glue(self, gen, module_name):
        return f'''
bool {self.check_func}(JSContext *, JSValueConst value) {{ return JS_IsNumber(value); }}
void {self.to_c_func}(JSContext *ctx, JSValueConst value, void *out) {{
    if (!JS_IsNumber(value)) qjs::type_error(ctx, "expected Number");
    double number;
    qjs::check(JS_ToFloat64(ctx, &number, value));
    *static_cast<{self.ctype} *>(out) = static_cast<{self.ctype}>(number);
}}
JSValue {self.from_c_func}(JSContext *ctx, void *object, OwnershipPolicy) {{
    return JS_NewFloat64(ctx, *static_cast<{self.ctype} *>(object));
}}
'''


class QuickJSConstCharPtrConverter(QuickJSTypeConverterCommon):
    def __init__(self, type='const char *'):
        super().__init__(type, needs_c_storage_class=True)

    def get_type_glue(self, gen, module_name):
        return f'''
struct {self.c_storage_class} {{ std::string value; }};
bool {self.check_func}(JSContext *, JSValueConst value) {{ return JS_IsString(value); }}
void {self.to_c_func}(JSContext *ctx, JSValueConst value, void *out, {self.c_storage_class} &storage) {{
    if (!JS_IsString(value)) qjs::type_error(ctx, "expected string");
    qjs::CString text(ctx, value);
    if (std::memchr(text.data, 0, text.size)) qjs::type_error(ctx, "embedded NUL in C string");
    storage.value.assign(text.data, text.size);
    *static_cast<const char **>(out) = storage.value.c_str();
}}
JSValue {self.from_c_func}(JSContext *ctx, void *object, OwnershipPolicy) {{
    const char *value = *static_cast<const char **>(object);
    return value ? JS_NewString(ctx, value) : JS_NULL;
}}
'''


def bind_std(gen):
    gen.bind_type(QuickJSBoolConverter('bool'))
    for type in ('char', 'short', 'int', 'long', 'int8_t', 'int16_t', 'int32_t', 'int64_t',
                 'char16_t', 'char32_t', 'unsigned char', 'unsigned short', 'unsigned int',
                 'unsigned long', 'uint8_t', 'uint16_t', 'uint32_t', 'uint64_t', 'intptr_t', 'uintptr_t', 'size_t'):
        gen.bind_type(QuickJSIntConverter(type))
    for type in ('float', 'double'):
        gen.bind_type(QuickJSFloatConverter(type))
    gen.bind_type(QuickJSConstCharPtrConverter())
