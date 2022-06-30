from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from pprint import pprint
import subprocess
from pathlib import Path
try:
    from functools import cached_property
except:
    cached_property = property
import multiprocessing
import sysconfig

class CustomBuildHook(BuildHookInterface):
    @cached_property
    def cmake_build_dir(self):
        p = Path(self.root) / "cmake_build"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @cached_property
    def cmake_install_dir(self):
        p = Path(self.root) / "install"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @cached_property
    def ogdf_src_dir(self):
        return Path(self.root) / "ogdf"

    def run(self, *args):
        return subprocess.run(map(str, args), capture_output=False, check=True, cwd=self.cmake_build_dir)

    def initialize(self, version, build_data):
        """
        This occurs immediately before each build.

        Any modifications to the build data will be seen by the build target.
        """
        print(self.run("cmake", self.ogdf_src_dir, "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=ON", "-DCMAKE_INSTALL_PREFIX=%s" % self.cmake_install_dir))
        print(self.run("cmake", "--build", ".", "--parallel", str(multiprocessing.cpu_count())))
        print(self.run("cmake", "--install", "."))
        build_data["pure_python"] = False
        build_data["tag"] = "py3-%s" % sysconfig.get_platform()

    def finalize(self, version, build_data, artifact_path):
        """
        This occurs immediately after each build and will not run if the `--hooks-only` flag
        was passed to the [`build`](../cli/reference.md#hatch-build) command.

        The build data will reflect any modifications done by the target during the build.
        """
        pass

    def clean(self, versions):
        """
        This occurs before the build process if the `-c`/`--clean` flag was passed to
        the [`build`](../cli/reference.md#hatch-build) command, or when invoking
        the [`clean`](../cli/reference.md#hatch-clean) command.
        """
        # print(self.run("make", "clean"))
        pass
