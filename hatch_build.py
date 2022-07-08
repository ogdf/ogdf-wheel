import multiprocessing
import os
import subprocess
import sysconfig
from pathlib import Path
from pprint import pprint

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

try:
    from functools import cached_property
except:
    cached_property = property


class CustomBuildHook(BuildHookInterface):
    @cached_property
    def cmake_build_dir(self):
        p = Path(self.directory) / "cmake_build"
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
        return subprocess.run(list(map(str, args)), capture_output=False, check=True, cwd=self.cmake_build_dir)

    def initialize(self, version, build_data):
        """
        This occurs immediately before each build.

        Any modifications to the build data will be seen by the build target.
        """
        # pprint(build_data)
        # pprint(self.build_config.__dict__)
        build_data["pure_python"] = False
        plat = os.getenv("AUDITWHEEL_PLAT", None)
        if not plat:
            plat = sysconfig.get_platform()
        build_data["tag"] = "py3-none-%s" % plat.replace("-", "_")
        print("Set wheel tag to", build_data["tag"])

        if "win" in build_data["tag"]:
            del self.build_config.target_config["shared-data"]
        else:
            del self.build_config.target_config["sources"]
        pprint(build_data)
        pprint(self.build_config.__dict__)

        # disable march=native optimizations (including SSE3)
        if os.environ.get("CIBUILDWHEEL", "0") == "1":
            comp_spec_cmake = self.ogdf_src_dir / "cmake" / "compiler-specifics.cmake"
            with open(comp_spec_cmake, "rt") as f:
                lines = f.readlines()
            with open(comp_spec_cmake, "wt") as f:
                f.writelines("# " + l if "march=native" in l and not l.strip().startswith("#") else l for l in lines)

        flags = [
            "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=ON", "-DCMAKE_INSTALL_PREFIX=%s" % self.cmake_install_dir,
            "-DCMAKE_BUILD_RPATH=$ORIGIN;@loader_path", "-DCMAKE_INSTALL_RPATH=$ORIGIN;@loader_path", "-DMACOSX_RPATH=TRUE",
        ]
        self.run("cmake", self.ogdf_src_dir, *flags)

        # windows needs Release config repeated but no parallel
        build_opts = []
        if "win" not in build_data["tag"]:
            build_opts = ["--parallel", str(multiprocessing.cpu_count())]
        self.run("cmake", "--build", ".", "--config", "Release", *build_opts)

        self.run("cmake", "--install", ".")

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
