"""Generation-time diagnostics that cannot be exercised by a native JS test."""
import unittest
import lib
from lang.quickjs import QuickJSGenerator
from lib.quickjs.stl import QuickJSArrayToStdVectorConverter


class QuickJSGeneratorDiagnostics(unittest.TestCase):
    def setUp(self):
        self.gen = QuickJSGenerator()
        self.gen.verbose = False
        self.gen.start('diagnostics')
        lib.bind_defaults(self.gen)

    def test_operator_name_collision(self):
        c = self.gen.begin_class('Vector')
        self.gen.bind_method(c, 'add', 'int', [])
        self.gen.bind_arithmetic_op(c, '+', 'Vector', ['const Vector &other'])
        with self.assertRaisesRegex(ValueError, r'Vector operator \+ collides with member add'):
            self.gen.end_class(c)

    def test_unknown_argument_names_offending_api(self):
        self.gen.bind_function('MissingAPI', 'void', ['UnknownHandle value'])
        with self.assertRaisesRegex(ValueError, 'function MissingAPI.*UnknownHandle'):
            self.gen.finalize()

    def test_callback_reference_result_rejected(self):
        with self.assertRaisesRegex(ValueError, 'GetBorrowed.*borrowed'):
            self.gen.rbind_function('GetBorrowed', 'int &', [])

    def test_temporary_string_array_rejected(self):
        with self.assertRaisesRegex(ValueError, 'temporary conversion storage'):
            QuickJSArrayToStdVectorConverter('Strings', self.gen.get_conv('const char *'))

    def test_unsupported_feature_names_offending_method(self):
        c = self.gen.begin_class('Object')
        with self.assertRaisesRegex(ValueError, 'method Run of Object.*async_magic'):
            self.gen.bind_method(c, 'Run', 'void', [], {'async_magic': True})

    def test_module_export_collision(self):
        c = self.gen.begin_class('Object')
        self.gen.end_class(c)
        self.gen.bind_function('make', 'void', [], bound_name='Object')
        with self.assertRaisesRegex(ValueError, 'duplicate export Object'):
            self.gen.finalize()


if __name__ == '__main__':
    unittest.main()
