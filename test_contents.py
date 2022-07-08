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


def match(p, k):
    if isinstance(p, str):
        return k.startswith(p)
    else:
        return p.fullmatch(k)


def partition(d, ps):
    r = defaultdict(dict)
    for k, v in d.items():
        for p in ps:
            if match(p, k):
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
    actual, expected = diff_dicts(actual, expected)
    for e in exp_a:
        if e not in actual:
            print("Missing file %s in %s!" % (e, tag))
            issues += 1
    sup = {k: v for k, v in actual.items() if not re.fullmatch(ign_a, k) and k not in exp_a}
    mis = {k: v for k, v in expected.items() if not re.fullmatch(ign_e, k)}
    if sup or mis:
        print("Mismatch for %s!\nSuperfluous:\n%s\nMissing:\n%s" % (tag, sup, mis))
        issues += 1


def ignore(*ps):
    return "|".join(p.replace(".", "\\.") for p in ps)


def check_wheel(wheelp, ogdfp, name, tag):
    name_esc = ignore(name)
    check_diff("wheel includes", wheelp[name + ".data/data/include/"], ogdfp["include/"],
               exp_a=["ogdf/basic/internal/config_autogen.h"])
    if "win" not in tag:
        check_diff("wheel examples", wheelp[name + ".data/data/share/doc/libogdf/examples/"], ogdfp["doc/examples/"],
                   ign_e=".*\\.dox")

    ign_meta = f"{name_esc}\\.dist-info/(METADATA|RECORD|WHEEL)|{name_esc}\\.data/data/lib/cmake/.*\.cmake|ogdf/.*LICENSE.*"
    if "win" in tag:
        check_diff("wheel rest", wheelp[""], {},
                   ign_a=ign_meta + "|install/lib/(COIN|OGDF)\.lib",
                   exp_a=["OGDF.dll", "ogdf/LICENSE.txt"])
    elif "macos" in tag:
        check_diff("wheel rest", wheelp[""], {},
                   ign_a=ign_meta,
                   exp_a=[name + ".data/data/lib/libOGDF.dylib", name + ".data/data/lib/libCOIN.dylib", "ogdf/LICENSE.txt"])
    else:
        check_diff("wheel rest", wheelp[""], {},
                   ign_a=ign_meta,
                   exp_a=[name + ".data/data/lib/libOGDF.so", name + ".data/data/lib/libCOIN.so", "ogdf/LICENSE.txt"])


def check_sdist(sdistp, ogdff):
    check_diff("sdist ogdf", sdistp["ogdf/"], ogdff,
               ign_e=ignore(".git", "doc/images/insertEdgePathEmbedded.svg"))
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
    @click.option('--ogdf', type=click.Path(exists=True, file_okay=False), required=True)
    @click.option('--sdist', type=click.Path(exists=True, dir_okay=False), required=False)
    @click.option('--wheel', type=click.Path(exists=True, dir_okay=False), required=False)
    @click.option('--name', type=str, required=True)
    @click.option('--dump', type=click.Path(file_okay=False), required=False)
    def main(ogdf, sdist, wheel, name, dump):
        ogdff = get_ogdf_files(ogdf)
        ogdfp = partition(ogdff, ["include/", "doc/examples/", "src/", "test/"])
        if dump: dump_data(dump, ogdff, ogdfp, "ogdf")

        if sdist:
            sdistf = get_sdist_files(sdist, name)
            sdistp = partition(sdistf, ["ogdf/"])
            if dump: dump_data(dump, sdistf, sdistp, "sdist")
            check_sdist(sdistp, ogdff)

        if wheel:
            wheelf = get_wheel_files(wheel, name)
            wheelp = partition(wheelf, [name + ".data/data/include/", name + ".data/data/share/doc/libogdf/examples/"])
            if dump: dump_data(dump, wheelf, wheelp, "wheel")
            check_wheel(wheelp, ogdfp, name, wheel)

        if issues:
            print("There were %s issue(s)!" % issues)
            click.get_current_context().exit(1)
        else:
            print("Everything looks good!")


    main()
