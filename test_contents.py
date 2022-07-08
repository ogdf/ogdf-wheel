import csv
import os
import re
import tarfile
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile


def get_sdist_files(file, name):
    file = Path(file)
    with tarfile.open(file) as tar:
        return {str(Path(f.name).relative_to(name)): f.size for f in tar.getmembers()}


def get_wheel_files(file, name):
    file = Path(file)
    with ZipFile(file) as zip:
        return {
            t[0]: (int(t[2]) if t[2] else None) for t in  # strip the sha256
            csv.reader(zip.read(name + ".dist-info/RECORD").decode("ascii").splitlines())
        }


def get_ogdf_files(base):
    infos = {}
    for root, dirs, files in os.walk(base):
        infos.update({
            str(path.relative_to(base)): path.stat().st_size
            for path in (Path(root, f) for f in files)
        })
    return infos


def partition(d, ps):
    r = defaultdict(dict)
    for k, v in d.items():
        for p in ps:
            if k.startswith(p):
                r[p][k[len(p):]] = v
                break
        else:
            r[""][k] = v
    return r


def diff_dicts(a, b):
    a, b = set(a.items()), set(b.items())
    return dict(sorted(a - b)), dict(sorted(b - a))


issues = 0


def check_diff(tag, actual, expected, ign_a="", ign_e="", exp_a=[]):
    global issues
    print("\tChecking", tag)
    actual, expected = diff_dicts(actual, expected)
    for e in exp_a:
        if e not in actual:
            print("\tMissing file %s in %s!" % (e, tag))
            issues += 1
    sup = {k: v for k, v in actual.items() if not re.fullmatch(ign_a, k) and k not in exp_a}
    mis = {k: v for k, v in expected.items() if not re.fullmatch(ign_e, k)}
    if sup or mis:
        print("\tMismatch for %s!\nSuperfluous:\n%s\nMissing:\n%s" % (tag, sup, mis))
        issues += 1


def ignore(*ps):
    return "|".join(p.replace(".", "\\.") for p in ps)


LICENSES = [
    "ogdf/LICENSE.txt",
    "ogdf/LICENSE_GPL_v2.txt",
    "ogdf/LICENSE_GPL_v3.txt",
    "ogdf/include/ogdf/lib/minisat/LICENSE",
]


def check_wheel(wheelp, ogdfp, name, tag):
    name_esc = ignore(name)
    headers, others = {}, {}
    for k, v in ogdfp["include/"].items():
        if re.match(".*\\.(h|hpp|inc)", k):
            headers[k] = v
        else:
            others[k] = v
    check_diff("wheel includes", wheelp[name + ".data/data/include/"], headers,
               exp_a=["ogdf/basic/internal/config_autogen.h"])
    check_diff("not installed wheel includes", others,
               {'coin/Readme.txt': 641,
                'ogdf/lib/.clang-tidy': 109,
                'ogdf/lib/minisat/LICENSE': 1142,
                'ogdf/lib/minisat/doc/ReleaseNotes-2.2.0.txt': 3418})
    if "win" not in tag:
        check_diff("wheel examples", wheelp[name + ".data/data/share/doc/libogdf/examples/"], ogdfp["doc/examples/"],
                   ign_e=".*\\.dox")

    ign_meta = f"{name_esc}\\.dist-info/(METADATA|RECORD|WHEEL)|{name_esc}\\.data/data/lib/cmake/.*\.cmake"
    exp_lic = [name + ".dist-info/license_files/" + f for f in LICENSES]
    if "win" in tag:
        check_diff("wheel rest [win]", wheelp[""], {},
                   ign_a=ign_meta + "|install/lib/(COIN|OGDF)\.lib",
                   exp_a=["OGDF.dll", *exp_lic])
    elif "macos" in tag:
        check_diff("wheel rest [macos]", wheelp[""], {},
                   ign_a=ign_meta,
                   exp_a=[name + ".data/data/lib/libOGDF.dylib", name + ".data/data/lib/libCOIN.dylib", *exp_lic])
    else:
        check_diff("wheel rest [linux]", wheelp[""], {},
                   ign_a=ign_meta,
                   exp_a=[name + ".data/data/lib/libOGDF.so", name + ".data/data/lib/libCOIN.so", *exp_lic])


def check_sdist(sdistp, ogdff):
    check_diff("sdist ogdf", sdistp["ogdf/"], ogdff,
               ign_e=ignore(".git", ".gitignore"))
    check_diff("sdist rest", sdistp[""], {},
               ign_a="\\.git.*|test_[a-z_]+\\.py",
               exp_a=['PKG-INFO', 'hatch_build.py', 'pyproject.toml'])


def dump_data(dumpdir, files, partitions, name):
    import json
    with open(dumpdir / name + "_files.csv", "w", newline="") as csvfile:
        csv.writer(csvfile).writerows(files.items())
    with open(dumpdir / name + "_files.json", "w") as jsonfile:
        json.dump(partitions, jsonfile)


if __name__ == "__main__":
    import click


    @click.command()
    @click.option('--dist', type=click.Path(exists=True, file_okay=False), default=Path("dist"))
    @click.option('--ogdf', type=click.Path(exists=True, file_okay=False), default=Path("ogdf"))
    @click.option('--dump', type=click.Path(file_okay=False))
    def main(dist, ogdf, dump):
        sdists = list(dist.glob("*.tar.gz"))
        if len(sdists) != 1:
            raise click.Abort("Didn't find exactly one source dist (.tar.gz) in %s: %s" % (dist, sdists))
        name = sdists[0].name.rsplit(".", 2)[0]

        ogdff = get_ogdf_files(ogdf)
        ogdfp = partition(ogdff, ["include/", "doc/examples/", "src/", "test/"])
        if dump: dump_data(dump, ogdff, ogdfp, "ogdf")

        checks = 0

        for sdist in dist.glob("*.tar.gz"):
            print("Checking", sdist)
            checks += 1
            sdistf = get_sdist_files(sdist, name)
            sdistp = partition(sdistf, ["ogdf/"])
            if dump: dump_data(dump, sdistf, sdistp, "sdist-%s" % sdist.name)
            check_sdist(sdistp, ogdff)

        for wheel in dist.glob("*.whl"):
            print("Checking", wheel)
            checks += 1
            wheelf = get_wheel_files(wheel, name)
            wheelp = partition(wheelf, [name + ".data/data/include/", name + ".data/data/share/doc/libogdf/examples/"])
            if dump: dump_data(dump, wheelf, wheelp, "wheel-%s" % wheel.name)
            check_wheel(wheelp, ogdfp, name, wheel.stem)

        if issues:
            print("There were %s issue(s)!" % issues)
            click.get_current_context().exit(1)
        elif not checks:
            print("No checks were run! Does the dist directory exist?")
            click.get_current_context().exit(1)
        else:
            print("Everything looks good!")


    main()
