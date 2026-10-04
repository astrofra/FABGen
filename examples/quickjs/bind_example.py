import lib


def bind(gen):
    gen.start('example')
    lib.bind_defaults(gen)
    gen.insert_code('''
struct Vec3 {
    float x, y, z;
    Vec3(float x=0, float y=0, float z=0) : x(x), y(y), z(z) {}
    Vec3 operator+(const Vec3 &b) const { return {x+b.x, y+b.y, z+b.z}; }
    Vec3 operator*(float k) const { return {x*k, y*k, z*k}; }
    bool operator==(const Vec3 &b) const { return x==b.x && y==b.y && z==b.z; }
};
int64_t timestamp() { return INT64_C(9007199254740993); }
bool project(const Vec3 &v, float &x, float &y) { x=v.x; y=v.y; return true; }
''', True, False)
    vector = gen.begin_class('Vec3')
    gen.bind_constructor(vector, ['?float x', '?float y', '?float z'])
    gen.bind_members(vector, ['float x', 'float y', 'float z'])
    gen.bind_arithmetic_op(vector, '+', 'Vec3', ['const Vec3 &b'])
    gen.bind_arithmetic_op(vector, '*', 'Vec3', ['float k'])
    gen.bind_comparison_op(vector, '==', ['const Vec3 &b'])
    gen.end_class(vector)
    gen.bind_function('timestamp', 'int64_t', [])
    gen.bind_function('project', 'bool', ['const Vec3 &v', 'float &x', 'float &y'], {'arg_out': ['x', 'y']})
    gen.finalize()
