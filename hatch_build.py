import multiprocessing
import os
import platform
import re
import subprocess
import sys
import sysconfig
from contextlib import contextmanager
from pathlib import Path
from pprint import pprint

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

try:
    from functools import cached_property
except:
    cached_property = property


def is_github_actions():
    return os.getenv("GITHUB_ACTIONS", None) == "true"


def is_cibuildwheel():
    return os.environ.get("CIBUILDWHEEL", "0") == "1"


def is_windows():
    return platform.system() == "Windows"


def is_macos():
    return platform.system() == "Darwin"


def sync():
    sys.stdout.flush()
    sys.stderr.flush()
    if hasattr(os, "sync"):
        os.sync()


@contextmanager
def group(*names):
    if is_github_actions():
        print("::group::%s" % " ".join(map(str, names)))
    else:
        print()
        print(*names)
    sync()
    yield
    sync()
    if is_github_actions():
        print("::endgroup::")
    else:
        print()


class CustomBuildHook(BuildHookInterface):
    @cached_property
    def tag(self):
        plat = os.getenv("AUDITWHEEL_PLAT", None)
        if not plat:
            plat = sysconfig.get_platform()
        return "py3-none-%s" % plat.replace("-", "_").replace(".", "_")

    def cmake_build_dir(self, config):
        p = Path(self.directory) / f"cmake_build_{config}"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @cached_property
    def cmake_install_dir(self):
        if is_windows():
            p = Path(self.root) / "src" / "ogdf_wheel" / "install"
        else:
            p = Path(self.root) / "install"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @cached_property
    def ogdf_src_dir(self):
        return Path(self.root) / "ogdf"

    def run(self, *args, dir):
        args = list(map(str, args))
        with group("Running", *args):
            return subprocess.run(args, capture_output=False, check=True, cwd=dir)

    def dump_files(self, dir):
        with group("Index of", dir):
            for dirpath, dirnames, filenames in os.walk(dir):
                for file in filenames:
                    print(dirpath + "/" + file)
                if not dirnames and not filenames:
                    print(dirpath, "(empty)")

    def initialize(self, version, build_data):
        """
        This occurs immediately before each build.

        Any modifications to the build data will be seen by the build target.
        """
        if is_cibuildwheel() and is_github_actions():
            print("::endgroup::")  # close the group from cibuildwheel

        build_data["pure_python"] = False
        build_data["tag"] = self.tag
        print("Set wheel tag to", build_data["tag"])

        if is_windows():
            del self.build_config.target_config["shared-data"]

        with group("Config"):
            pprint({
                "root": self.root,
                "directory": self.directory,
                "ogdf_src_dir": self.ogdf_src_dir,
                "cmake_install_dir": self.cmake_install_dir,
                "cmake_build_dir debug": self.cmake_build_dir("debug"),
                "cmake_build_dir release": self.cmake_build_dir("release"),
            })
            pprint(build_data)
            pprint(self.build_config.__dict__)

        # remove version information from .so name
        cmake_file = self.ogdf_src_dir / "CMakeLists.txt"
        with open(cmake_file, "rt") as f:
            lines = f.readlines()
        with open(cmake_file, "wt") as f:
            f.writelines(re.sub(' *VERSION "20[0-9.]+"', '', l) for l in lines)

        flags = [
            "-DBUILD_SHARED_LIBS=ON",
            "-DCMAKE_INSTALL_PREFIX=%s" % self.cmake_install_dir,
            "-DOGDF_WARNING_ERRORS=OFF",
            "-DCMAKE_BUILD_RPATH=$ORIGIN;@loader_path", "-DCMAKE_INSTALL_RPATH=$ORIGIN;@loader_path",
            "-DMACOSX_RPATH=TRUE",
            "-DCMAKE_INSTALL_LIBDIR=lib",  # instead of lib64 https://stackoverflow.com/a/76528304
        ]
        if is_windows():
            flags.append("-DOGDF_MEMORY_MANAGER=MALLOC_TS")
        else:
            flags.append("-DOGDF_MEMORY_MANAGER=POOL_TS")

        release_dir = self.cmake_build_dir("release")
        self.run("cmake", self.ogdf_src_dir, "-DCMAKE_BUILD_TYPE=Release", *flags, dir=release_dir)
        self.run("cmake", "--build", ".", "--config", "Release", "--parallel", str(multiprocessing.cpu_count()),
                 dir=release_dir)
        self.run("cmake", "--install", ".", "--config", "Release", dir=release_dir)

        if not is_windows():
            flags.extend([
                "-DOGDF_USE_ASSERT_EXCEPTIONS=ON",  # "-DOGDF_USE_ASSERT_EXCEPTIONS_WITH=ON_LIBUNWIND",
            ])
        debug_dir = self.cmake_build_dir("debug")
        self.run("cmake", self.ogdf_src_dir, "-DCMAKE_BUILD_TYPE=Debug", *flags, dir=debug_dir)
        self.run("cmake", "--build", ".", "--config", "Debug", "--parallel", str(multiprocessing.cpu_count()),
                 dir=debug_dir)
        self.run("cmake", "--install", ".", "--config", "Debug", dir=debug_dir)

        # import IPython
        # IPython.embed()

        self.dump_files(self.directory)
        self.dump_files(self.root)

    def finalize(self, version, build_data, artifact_path):
        """
        This occurs immediately after each build and will not run if the `--hooks-only` flag
        was passed to the [`build`](../cli/reference.md#hatch-build) command.

        The build data will reflect any modifications done by the target during the build.
        """
        with group("Wheel files RECORD"):
            from zipfile import ZipFile
            with ZipFile(artifact_path) as zip:
                print(zip.read(self.build_config.builder.project_id + ".dist-info/RECORD").decode("ascii"))

    def clean(self, versions):
        """
        This occurs before the build process if the `-c`/`--clean` flag was passed to
        the [`build`](../cli/reference.md#hatch-build) command, or when invoking
        the [`clean`](../cli/reference.md#hatch-clean) command.
        """
        import shutil
        shutil.rmtree(self.cmake_build_dir("release"), ignore_errors=True)
        shutil.rmtree(self.cmake_build_dir("debug"), ignore_errors=True)
        shutil.rmtree(self.cmake_install_dir, ignore_errors=True)
