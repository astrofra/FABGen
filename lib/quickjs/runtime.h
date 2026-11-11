// Shared by all generated QuickJS translation units in a host. C++14.
#pragma once
#include <quickjs.h>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>

namespace fabgen_quickjs {
// An exception already stored in the context. Never crosses a QuickJS callback.
struct PendingException {};

class Value {
public:
    JSContext *ctx;
    JSValue value;
    explicit Value(JSContext *ctx, JSValue value = JS_UNDEFINED) : ctx(ctx), value(value) {}
    ~Value() { JS_FreeValue(ctx, value); }
    Value(const Value &) = delete;
    Value &operator=(const Value &) = delete;
    Value(Value &&other) noexcept : ctx(other.ctx), value(other.release()) {}
    operator JSValue() const { return value; }
    JSValue release() { JSValue result = value; value = JS_UNDEFINED; return result; }
    Value &operator=(JSValue next) {
        JS_FreeValue(ctx, value); value = next; return *this;
    }
};

inline JSValue checked(JSValue value) {
    if (JS_IsException(value)) throw PendingException();
    return value;
}
inline void check(int status) { if (status < 0) throw PendingException(); }
inline void type_error(JSContext *ctx, const char *message) {
    JS_ThrowTypeError(ctx, "%s", message); throw PendingException();
}
inline void range_error(JSContext *ctx, const char *message) {
    JS_ThrowRangeError(ctx, "%s", message); throw PendingException();
}
class CString {
public:
    JSContext *ctx;
    size_t size = 0;
    const char *data;
    CString(JSContext *ctx, JSValueConst value) : ctx(ctx), data(JS_ToCStringLen(ctx, &size, value)) {
        if (!data) throw PendingException();
    }
    ~CString() { JS_FreeCString(ctx, data); }
    CString(const CString &) = delete;
};

// BigInt's decimal representation is exact; JS_ToBigInt64 itself wraps modulo
// 2^64 and therefore cannot validate overflow. No user coercion hooks run here.
template <typename T> bool integer(JSContext *ctx, JSValueConst value, T *out = nullptr) {
    static_assert(std::is_integral<T>::value, "integer converter requires an integer");
    if (JS_IsNumber(value)) {
        double number;
        check(JS_ToFloat64(ctx, &number, value));
        if (!std::isfinite(number) || std::trunc(number) != number ||
            std::fabs(number) > 9007199254740991.0) return false;
        // Compare powers of two, not rounded floating representations of MAX.
        const double limit = std::ldexp(1.0, std::numeric_limits<T>::digits);
        if (number >= limit || number < (std::is_signed<T>::value ? -limit : 0.0)) return false;
        if (out) *out = static_cast<T>(number);
        return true;
    }
    if (sizeof(T) < 8 || !JS_IsBigInt(ctx, value)) return false;
    CString str(ctx, value);
    const char *p = str.data;
    const bool negative = *p == '-';
    if (negative) ++p;
    if (negative && !std::is_signed<T>::value) return false;
    const uint64_t maximum = std::is_signed<T>::value
        ? (negative ? uint64_t(INT64_MAX) + 1 : uint64_t(INT64_MAX)) : UINT64_MAX;
    uint64_t magnitude = 0;
    for (; *p; ++p) {
        unsigned digit = unsigned(*p - '0');
        if (digit > 9 || magnitude > (maximum - digit) / 10) return false;
        magnitude = magnitude * 10 + digit;
    }
    if (out) {
        if (negative) *out = magnitude == uint64_t(INT64_MAX) + 1
            ? static_cast<T>(INT64_MIN) : static_cast<T>(-static_cast<int64_t>(magnitude));
        else *out = static_cast<T>(magnitude);
    }
    return true;
}
template <typename T> JSValue new_integer(JSContext *ctx, T value) {
    if (sizeof(T) >= 8) return std::is_signed<T>::value
        ? JS_NewBigInt64(ctx, static_cast<int64_t>(value))
        : JS_NewBigUint64(ctx, static_cast<uint64_t>(value));
    return JS_NewFloat64(ctx, static_cast<double>(value));
}

struct Native {
    uint32_t tag;
    void *object;
    void (*destroy)(void *);
    bool (*can_cast)(uint32_t, uint32_t);
    void *(*cast)(void *, uint32_t, uint32_t);
    std::vector<JSValue> parents;
};
inline Native *make_native(uint32_t tag, void *object, void (*destroy)(void *),
                          bool (*can_cast)(uint32_t, uint32_t), void *(*cast)(void *, uint32_t, uint32_t)) {
    try { return new Native{tag, object, destroy, can_cast, cast, {}}; }
    catch (...) { if (destroy) destroy(object); throw; }
}
inline JSClassID native_class_id() {
    static JSClassID id = [] { JSClassID id = 0; JS_NewClassID(&id); return id; }();
    return id;
}
inline Native *native(JSValueConst value) {
    return static_cast<Native *>(JS_GetOpaque(value, native_class_id()));
}
inline void native_finalizer(JSRuntime *rt, JSValue value) {
    auto *obj = native(value);
    if (!obj) return;
    if (obj->destroy) obj->destroy(obj->object);
    for (auto parent : obj->parents) JS_FreeValueRT(rt, parent);
    delete obj;
}
inline void native_mark(JSRuntime *rt, JSValueConst value, JS_MarkFunc *mark) {
    auto *obj = native(value);
    if (obj) for (auto parent : obj->parents) JS_MarkValue(rt, parent, mark);
}
inline void ensure_native_class(JSContext *ctx) {
    JSRuntime *rt = JS_GetRuntime(ctx);
    auto id = native_class_id();
    if (!JS_IsRegisteredClass(rt, id)) {
        JSClassDef def = {};
        def.class_name = "FABGenNative";
        def.finalizer = native_finalizer;
        def.gc_mark = native_mark;
        check(JS_NewClass(rt, id, &def));
    }
    Value registry(ctx, JS_GetClassProto(ctx, id));
    if (!JS_IsObject(registry)) JS_SetClassProto(ctx, id, checked(JS_NewObjectProto(ctx, JS_NULL)));
}
inline JSValue registry(JSContext *ctx) {
    ensure_native_class(ctx);
    return JS_GetClassProto(ctx, native_class_id());
}
inline void keep_alive(JSContext *ctx, JSValueConst child, JSValueConst parent) {
    auto *obj = native(child);
    if (obj && JS_IsObject(parent) && JS_VALUE_GET_PTR(child) != JS_VALUE_GET_PTR(parent)) {
        // Reserve before duplicating so allocation failure cannot leak the handle.
        obj->parents.reserve(obj->parents.size() + 1);
        obj->parents.push_back(JS_DupValue(ctx, parent));
    }
}

// A borrowed result conservatively retains its native receiver and arguments.
struct CallScope {
    JSContext *ctx;
    JSValueConst self;
    int argc;
    JSValueConst *argv;
    CallScope *previous;
    static CallScope *&current() { static thread_local CallScope *scope = nullptr; return scope; }
    CallScope(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
        : ctx(ctx), self(self), argc(argc), argv(argv), previous(current()) { current() = this; }
    ~CallScope() { current() = previous; }
};
inline JSValue wrap(JSContext *ctx, const char *type, Native *raw, bool borrowed) {
    auto cleanup = [](Native *p) { if (p->destroy) p->destroy(p->object); delete p; };
    std::unique_ptr<Native, decltype(cleanup)> obj(raw, cleanup);
    Value reg(ctx, registry(ctx));
    Value proto(ctx, checked(JS_GetPropertyStr(ctx, reg, type)));
    if (!JS_IsObject(proto)) proto = JS_NULL; // opaque pointers have no public prototype
    Value result(ctx, JS_NewObjectProtoClass(ctx, proto, native_class_id()));
    if (JS_IsException(result)) {
        throw PendingException();
    }
    JS_SetOpaque(result, obj.release());
    auto *scope = CallScope::current();
    if (borrowed && scope && scope->ctx == ctx) {
        keep_alive(ctx, result, scope->self);
        for (int i = 0; i < scope->argc; ++i) keep_alive(ctx, result, scope->argv[i]);
    }
    return result.release();
}
inline bool is_native(JSValueConst value, uint32_t tag) {
    auto *obj = native(value);
    return obj && obj->object && (obj->tag == tag || (obj->can_cast && obj->can_cast(obj->tag, tag)));
}
inline void *unwrap(JSContext *ctx, JSValueConst value, uint32_t tag) {
    if (JS_IsNull(value)) return nullptr;
    auto *obj = native(value);
    if (!is_native(value, tag)) type_error(ctx, "invalid native object or incompatible native type");
    return obj->tag == tag ? obj->object : obj->cast(obj->object, obj->tag, tag);
}
template <typename T> void destroy(void *object) { delete static_cast<T *>(object); }

struct Callback;
struct ContextState {
    std::thread::id thread = std::this_thread::get_id();
    std::vector<std::weak_ptr<Callback>> callbacks;
    std::map<std::string, bool> modules;
};
inline std::map<JSContext *, ContextState> &contexts() {
    static std::map<JSContext *, ContextState> states;
    return states;
}
inline std::recursive_mutex &context_mutex() { static std::recursive_mutex mutex; return mutex; }
struct Callback {
    JSContext *ctx;
    JSValue function;
    std::thread::id thread;
    Callback(JSContext *ctx, JSValueConst function)
        : ctx(ctx), function(JS_DupValue(ctx, function)), thread(std::this_thread::get_id()) {}
    ~Callback() { clear(); }
    void clear() { if (ctx) { JS_FreeValue(ctx, function); ctx = nullptr; function = JS_UNDEFINED; } }
    void require_live() const {
        if (!ctx) throw std::runtime_error("QuickJS callback used after binding release");
        if (thread != std::this_thread::get_id()) throw std::runtime_error("QuickJS callback called from another thread");
    }
};
inline std::shared_ptr<Callback> retain_callback(JSContext *ctx, JSValueConst function) {
    auto ref = std::make_shared<Callback>(ctx, function);
    std::lock_guard<std::recursive_mutex> lock(context_mutex());
    auto &refs = contexts()[ctx].callbacks;
    // Prune expired handles to keep transient callbacks bounded.
    for (auto i = refs.begin(); i != refs.end();) {
        if (i->expired()) i = refs.erase(i); else ++i;
    }
    refs.push_back(ref);
    return ref;
}
inline bool begin_module(JSContext *ctx, const char *name) {
    std::lock_guard<std::recursive_mutex> lock(context_mutex());
    auto &modules = contexts()[ctx].modules;
    return modules.emplace(name, true).second;
}
inline bool end_module(JSContext *ctx, const char *name) {
    std::lock_guard<std::recursive_mutex> lock(context_mutex());
    auto i = contexts().find(ctx);
    return i != contexts().end() && i->second.modules.erase(name) != 0;
}
inline void release_context(JSContext *ctx) {
    std::vector<std::weak_ptr<Callback>> refs;
    {
        std::lock_guard<std::recursive_mutex> lock(context_mutex());
        auto i = contexts().find(ctx);
        if (i == contexts().end()) return;
        // Each generated module runs its own custom cleanup. The last release
        // invalidates callbacks shared across the linked modules.
        if (!i->second.modules.empty()) return;
        if (i->second.thread != std::this_thread::get_id())
            throw std::runtime_error("release QuickJS bindings on the context's owning thread");
        refs.swap(i->second.callbacks);
        contexts().erase(i);
    }
    for (auto &weak : refs) if (auto ref = weak.lock()) ref->clear();
}

inline void property(JSContext *ctx, JSValueConst object, const char *name, JSValue value) {
    checked(value);
    check(JS_DefinePropertyValueStr(ctx, object, name, value, JS_PROP_C_W_E));
}
inline void method(JSContext *ctx, JSValueConst object, const char *name, JSCFunction *fn, int argc) {
    property(ctx, object, name, JS_NewCFunction(ctx, fn, name, argc));
}
inline void accessor(JSContext *ctx, JSValueConst object, const char *name, JSCFunction *get, JSCFunction *set) {
    JSAtom atom = JS_NewAtom(ctx, name);
    if (atom == JS_ATOM_NULL) throw PendingException();
    Value getter(ctx, JS_NewCFunction(ctx, get, name, 0));
    Value setter(ctx, set ? JS_NewCFunction(ctx, set, name, 1) : JS_UNDEFINED);
    if (JS_IsException(getter) || JS_IsException(setter)) { JS_FreeAtom(ctx, atom); throw PendingException(); }
    int status = JS_DefinePropertyGetSet(ctx, object, atom, getter.release(), setter.release(), JS_PROP_CONFIGURABLE | JS_PROP_ENUMERABLE);
    JS_FreeAtom(ctx, atom);
    check(status);
}
// Read data elements only. Accessors/holes are rejected rather than executing
// user code repeatedly while overloads are probed.
inline bool is_array(JSContext *ctx, JSValueConst value) {
    static JSClassID id = [ctx] { Value sample(ctx, checked(JS_NewArray(ctx))); return JS_GetClassID(sample); }();
    return JS_GetClassID(value) == id; // JS_IsArray also accepts proxies
}
inline bool is_record(JSContext *ctx, JSValueConst value) {
    static JSClassID id = [ctx] { Value sample(ctx, checked(JS_NewObject(ctx))); return JS_GetClassID(sample); }();
    return JS_GetClassID(value) == id;
}
inline JSValue array_element(JSContext *ctx, JSValueConst array, uint32_t index) {
    JSAtom atom = JS_NewAtomUInt32(ctx, index);
    if (atom == JS_ATOM_NULL) throw PendingException();
    JSPropertyDescriptor desc = {};
    int found = JS_GetOwnProperty(ctx, &desc, array, atom);
    JS_FreeAtom(ctx, atom);
    check(found);
    if (!found) type_error(ctx, "sparse arrays are not accepted");
    Value getter(ctx, desc.getter), setter(ctx, desc.setter), value(ctx, desc.value);
    if ((desc.flags & JS_PROP_TMASK) == JS_PROP_GETSET) type_error(ctx, "array accessors are not accepted");
    return value.release();
}
inline uint32_t array_length(JSContext *ctx, JSValueConst array) {
    Value length(ctx, checked(JS_GetPropertyStr(ctx, array, "length")));
    uint32_t count;
    if (!integer(ctx, length, &count)) type_error(ctx, "invalid array length");
    return count;
}
struct OwnProperties {
    JSContext *ctx;
    JSPropertyEnum *names = nullptr;
    uint32_t count = 0;
    OwnProperties(JSContext *ctx, JSValueConst value) : ctx(ctx) {
        check(JS_GetOwnPropertyNames(ctx, &names, &count, value, JS_GPN_STRING_MASK | JS_GPN_ENUM_ONLY));
    }
    ~OwnProperties() {
        for (uint32_t i = 0; i < count; ++i) JS_FreeAtom(ctx, names[i].atom);
        js_free(ctx, names);
    }
    OwnProperties(const OwnProperties &) = delete;
};
} // namespace fabgen_quickjs
