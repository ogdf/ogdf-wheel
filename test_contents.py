import csv
import os
import re
import tarfile
from collections import defaultdict
from functools import partial
from pathlib import Path
from textwrap import indent
from zipfile import ZipFile

IGNORE_GIT = "\\.git.*|.*\\.gitignore|.*\\.patch"


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


def diff_dict_keys(a, b):
    A, B = set(a.keys()), set(b.keys())
    return {k: a[k] for k in sorted(A - B)}, {k: b[k] for k in sorted(B - A)}


issues = 0


def check_diff(tag, actual, expected, ign_a="", ign_e="", exp_a=[], win=False):
    global issues
    print("\tChecking", tag)
    if win:
        actual, expected = diff_dict_keys(actual, expected)
    else:
        actual, expected = diff_dicts(actual, expected)
    for e in exp_a:
        if e not in actual:
            print("\tMissing file %s in %s!" % (e, tag))
            issues += 1
    sup = {k: v for k, v in actual.items() if not re.fullmatch(ign_a, k) and k not in exp_a}
    mis = {k: v for k, v in expected.items() if not re.fullmatch(ign_e, k)}
    if sup or mis:
        print(("\tMismatch for %s!\n" % tag) + indent("Superfluous:\n%s\nMissing:\n%s" % (sup, mis), "\t\t"))
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

    # _cur is the install location for the current platform (UNIX), _oth for the other (Windows)
    incl_cur, incl_oth = wheelp[name + ".data/data/include/"], wheelp["ogdf_wheel/install/include/"]
    exam_cur, exam_oth = wheelp[name + ".data/data/share/doc/libogdf/examples/"], wheelp["ogdf_wheel/install/share/doc/libogdf/examples/"]
    check = check_diff
    if "win" in tag:
        incl_cur, incl_oth = incl_oth, incl_cur
        exam_cur, exam_oth = exam_oth, exam_cur
        check = partial(check_diff, win=True)

    check("wheel includes [cur]", incl_cur, headers, exp_a=["ogdf/basic/internal/config_autogen.h"])
    check("wheel includes [oth]", incl_oth, {})
    check("wheel examples [cur]", exam_cur, ogdfp["doc/examples/"], ign_e=IGNORE_GIT + "|.*\\.dox")
    check("wheel examples [oth]", exam_oth, {})

    check("not installed wheel includes", others,
          {'coin/Readme.txt': 641,
           'ogdf/lib/.clang-tidy': 109,
           'ogdf/lib/minisat/LICENSE': 1142,
           'ogdf/lib/minisat/doc/ReleaseNotes-2.2.0.txt': 3418,
           'ogdf/geometric/README.md': 321})

    ign_meta = f"{name_esc}\\.dist-info/(METADATA|RECORD|WHEEL)|{name_esc}\\.data/data/lib/cmake/.*\.cmake"
    exp_lic = [name + ".dist-info/licenses/" + f for f in LICENSES] + ['ogdf_wheel/__init__.py']
    if "win" in tag:
        check("wheel install [win]", wheelp["ogdf_wheel/install/"], {},
              ign_a="lib/cmake/.*\.cmake|lib/(COIN|OGDF)\.lib",
              exp_a=["bin/OGDF.dll"])
        check("wheel rest [win]", wheelp[""], {}, ign_a=ign_meta, exp_a=exp_lic)
    elif "macos" in tag:
        check("wheel rest [macos]", wheelp[""], {},
              ign_a=ign_meta,
              exp_a=[name + ".data/data/lib/libOGDF.dylib", name + ".data/data/lib/libCOIN.dylib", *exp_lic])
    else:
        check("wheel rest [linux]", wheelp[""], {},
              ign_a=ign_meta,
              exp_a=[name + ".data/data/lib/libOGDF.so", name + ".data/data/lib/libCOIN.so", *exp_lic])


def check_sdist(sdistp, ogdff):
    check_diff("sdist ogdf", sdistp["ogdf/"], ogdff,
               ign_e=IGNORE_GIT)
    check_diff("sdist rest", sdistp[""], {},
               ign_a=IGNORE_GIT + "|test_[a-z_]+\\.py",
               exp_a=['PKG-INFO', 'hatch_build.py', 'pyproject.toml', 'src/ogdf_wheel/__init__.py', 'README.md'])


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
        dist = Path(dist)
        ogdf = Path(ogdf)
        dump = Path(dump) if dump else dump

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
            wheelp = partition(wheelf, [
                name + ".data/data/include/", name + ".data/data/share/doc/libogdf/examples/",
                "ogdf_wheel/install/include/", "ogdf_wheel/install/share/doc/libogdf/examples/", "ogdf_wheel/install/"])
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
