"""Native test bed, shared by tests.py; builds QuickJS core once per suite."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


class QuickJSTestBed:
    def __init__(self, source, compiler=None, cxx=None, debug=False):
        if compiler and Path(compiler).exists():
            compiler = str(Path(compiler).resolve())
        if cxx and Path(cxx).exists():
            cxx = str(Path(cxx).resolve())
        self.source = Path(source).resolve()
        version = (self.source / 'VERSION').read_text().strip()
        if version != '2026-06-04':
            raise ValueError('QuickJS tests require official 2026-06-04; found ' + version)
        self.cc = [compiler or os.environ.get('CC', 'cc')]
        self.cxx = [cxx or os.environ.get('CXX', 'c++')]
        if compiler and Path(compiler).stem == 'zig':
            self.cc += ['cc']
            self.cxx = [compiler, 'c++']
        self.cache = tempfile.TemporaryDirectory(prefix='fabgen-quickjs-')
        # Upstream VERSION shadows C++ <version> on case-insensitive systems.
        include = Path(self.cache.name) / 'include'
        include.mkdir()
        shutil.copyfile(self.source / 'quickjs.h', include / 'quickjs.h')
        self.flags = ['-g', '-O0' if debug else '-O2', '-fwrapv', '-I' + str(include)]
        self.objects = []
        for source in ('quickjs.c', 'dtoa.c', 'libregexp.c', 'libunicode.c', 'cutils.c'):
            obj = str(Path(self.cache.name) / (source + '.o'))
            cmd = self.cc + self.flags + ['-std=gnu11', '-include', 'stddef.h', '-D_GNU_SOURCE', '-DCONFIG_VERSION="2026-06-04"']
            if os.name == 'nt':
                cmd += ['-D__USE_MINGW_ANSI_STDIO']
            self.run(cmd + ['-c', str(self.source / source), '-o', obj])
            self.objects.append(obj)

    @staticmethod
    def run(command, cwd=None):
        try:
            subprocess.run(command, cwd=cwd, check=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=300)
        except subprocess.CalledProcessError as error:
            print('Command failed with exit code %s: %s' % (error.returncode, command[0]))
            print(error.stdout.decode('utf-8', errors='replace'))
            raise

    def get_skip_reason(self, module):
        return None if hasattr(module, 'test_quickjs') else 'missing test_quickjs'

    def build_and_test_extension(self, work_path, module, sources):
        root = Path(__file__).resolve().parent
        host = (root / 'tests' / 'quickjs_host.cpp').read_text(encoding='utf-8')
        if hasattr(module, 'quickjs_host_transform'):
            host = module.quickjs_host_transform(host)
        (Path(work_path) / 'host.cpp').write_text(host, encoding='utf-8')
        prelude = getattr(module, 'quickjs_import', 'import * as my_test from "my_test";\n') + '''function assert(value, message = "assertion failed") { if (!value) throw new Error(message); }
function throws(fn, type = TypeError) { let caught = false; try { fn(); } catch (e) { caught = true; assert(e instanceof type, String(e)); } assert(caught, "expected exception"); }
'''
        (Path(work_path) / 'test.mjs').write_text(prelude + module.test_quickjs, encoding='utf-8')
        executable = str(Path(work_path) / ('test.exe' if os.name == 'nt' else 'test'))
        try:
            command = self.cxx + self.flags + ['-std=c++14', '-I' + work_path] + sources + ['host.cpp'] + self.objects
            command += ['-lm', '-lpthread']
            if os.name != 'nt':
                command += ['-ldl']
            self.run(command + ['-o', executable], cwd=work_path)
            self.run([executable, str(Path(work_path) / 'test.mjs')], cwd=work_path)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            if isinstance(error, subprocess.TimeoutExpired):
                print('QuickJS test timed out:', error.cmd)
            return False
