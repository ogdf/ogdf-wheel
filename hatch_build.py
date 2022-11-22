import multiprocessing
import os
import platform
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

    @cached_property
    def cmake_build_dir(self):
        p = Path(self.directory) / "cmake_build"
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

    def run(self, *args):
        args = list(map(str, args))
        with group("Running", *args):
            return subprocess.run(args, capture_output=False, check=True, cwd=self.cmake_build_dir)

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
            pprint(build_data)
            pprint(self.build_config.__dict__)

        # disable march=native optimizations (including SSE3)
        if is_cibuildwheel():
            comp_spec_cmake = self.ogdf_src_dir / "cmake" / "compiler-specifics.cmake"
            with open(comp_spec_cmake, "rt") as f:
                lines = f.readlines()
            with open(comp_spec_cmake, "wt") as f:
                f.writelines("# " + l if "march=native" in l and not l.strip().startswith("#") else l for l in lines)

        CONFIG = "Debug"
        flags = [
            "-DCMAKE_BUILD_TYPE=" + CONFIG, "-DBUILD_SHARED_LIBS=ON", "-DCMAKE_INSTALL_PREFIX=%s" % self.cmake_install_dir,
            "-DOGDF_USE_ASSERT_EXCEPTIONS=ON",  # "-DOGDF_USE_ASSERT_EXCEPTIONS_WITH=ON_LIBUNWIND",
            "-DOGDF_MEMORY_MANAGER=POOL_TS",
            # "-DOGDF_MEMORY_MANAGER=MALLOC_TS", "-DOGDF_LEAK_CHECK=ON",
            "-DOGDF_WARNING_ERRORS=OFF",
            "-DCMAKE_BUILD_RPATH=$ORIGIN;@loader_path", "-DCMAKE_INSTALL_RPATH=$ORIGIN;@loader_path", "-DMACOSX_RPATH=TRUE",
        ]
        self.run("cmake", self.ogdf_src_dir, *flags)

        # import IPython
        # IPython.embed()

        # windows needs config repeated but no parallel
        build_opts = []
        if not is_windows():
            build_opts = ["--parallel", str(multiprocessing.cpu_count())]
        self.run("cmake", "--build", ".", "--config", CONFIG, *build_opts)

        self.run("cmake", "--install", ".", "--config", CONFIG)

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
        shutil.rmtree(self.cmake_build_dir)
        shutil.rmtree(self.cmake_install_dir)
