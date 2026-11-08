#!/usr/bin/env python3
"""Assemble LionKit (modern curl + WebP tools for OS X Lion) from MacPorts' signed darwin_11 builds
and install it on the Mac at ~/Library/LionKit.

usage: tools/build_lionkit.py [--no-install]

Only curl, dwebp and the libraries they really load are kept. Each library is copied once under
its real name, and the install names that differ from it become relative symlinks. Lion has no
otool and this Linux box has no Mach-O reader, so the load commands are read on the Mac with the
macholib in Lion's Python Extras. That step needs the Mac even with --no-install.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import fetch_macports  # noqa: E402

# (port, archive) roots; fetch_macports resolves and verifies every dependency.
ROOTS = [
    ("curl", "curl-8.23.0_1+brotli+http2+idn+psl+ssl+zstd.darwin_11.x86_64.tbz2"),
    ("webp", "webp-1.6.0_0.darwin_11.x86_64.tbz2"),
]
BINARIES = ["curl", "dwebp"]
WRAPPERS = {
    "lk-curl": 'DYLD_LIBRARY_PATH="$LK/lib" exec "$LK/bin/curl" --cacert "$LK/share/curl-ca-bundle.crt" "$@"',
    "lk-dwebp": 'DYLD_LIBRARY_PATH="$LK/lib" exec "$LK/bin/dwebp" "$@"',
}
PREFIX = "/opt/local/"
STAGE = TOOLS / "stage"
OUT = TOOLS / "LionKit"
HOST = os.environ.get("LION_HOST", "lionmac")

# Runs on the Mac with /usr/bin/python (2.7), whose path includes Lion's macholib.
# argv[1] is a folder of Mach-O files; prints {file: [install names it loads]} and the
# names outside /opt/local that Lion doesn't have.
MACHO_DEPS = r'''
import json, os, sys
from macholib.MachO import MachO
from macholib.mach_o import LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LAZY_LOAD_DYLIB
from macholib.ptypes import sizeof
LOADS = (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LAZY_LOAD_DYLIB)
deps, missing = {}, set()
for name in os.listdir(sys.argv[1]):
    names = deps.setdefault(name, [])
    for header in MachO(os.path.join(sys.argv[1], name)).headers:
        for lc, cmd, data in header.commands:
            if lc.cmd in LOADS:
                ofs = cmd.name - sizeof(lc.__class__) - sizeof(cmd.__class__)
                dylib = data[ofs:data.find("\0", ofs)]
                names.append(dylib)
                if not dylib.startswith(("/opt/local/", "@")) and not os.path.exists(dylib):
                    missing.add(dylib)
print(json.dumps({"deps": deps, "missing": sorted(missing)}))
'''


def real(path):
    """Resolve symlinks whose targets are absolute /opt/local paths inside the stage dir."""
    for _ in range(20):
        if not path.is_symlink():
            return path
        target = os.readlink(path)
        path = Path(str(STAGE) + target) if target.startswith("/") else path.parent / target
        path = Path(os.path.normpath(path))
    sys.exit("symlink loop at %s" % path)


def load_commands(files):
    """Ship the Mach-O files to the Mac and read their dylib load commands there."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        script = MACHO_DEPS.encode()
        info = tarfile.TarInfo("deps.py")
        info.size = len(script)
        t.addfile(info, io.BytesIO(script))
        for i, f in enumerate(files):
            t.add(str(f), arcname="files/%d" % i)
    out = subprocess.run(["ssh", "-o", "BatchMode=yes", HOST,
                          'D=$(mktemp -d /tmp/lk-macho.XXXXXX) && tar -xzf - -C "$D" && '
                          '/usr/bin/python "$D/deps.py" "$D/files"; S=$?; rm -rf "$D"; exit $S'],
                         input=buf.getvalue(), stdout=subprocess.PIPE, check=True)
    result = json.loads(out.stdout)
    if result["missing"]:
        sys.exit("these system libraries aren't on Lion: %s" % ", ".join(result["missing"]))
    return {files[int(i)]: names for i, names in result["deps"].items()}


def closure(local):
    """Map each install-name leaf that dyld will look up to the real file in the stage."""
    roots = [local / "bin" / name for name in BINARIES]
    dylibs = sorted(p for p in local.rglob("*.dylib") if not p.is_symlink())
    deps = load_commands([real(p) for p in roots] + dylibs)
    leaves, queue, seen = {}, [real(p) for p in roots], set()
    while queue:
        f = queue.pop()
        if f in seen:
            continue
        seen.add(f)
        for name in deps[f]:
            if name.startswith("@"):
                sys.exit("%s loads %s; @-relative install names aren't handled" % (f.name, name))
            if not name.startswith(PREFIX):
                continue  # Lion's own /usr/lib and /System libraries
            lib = real(STAGE / name.lstrip("/"))
            if lib not in deps:
                sys.exit("%s loads %s, which no package provides" % (f.name, name))
            if leaves.setdefault(os.path.basename(name), lib) != lib:
                sys.exit("two different libraries are both loaded as %s" % os.path.basename(name))
            queue.append(lib)
    return leaves


def extract():
    shutil.rmtree(STAGE, ignore_errors=True)
    STAGE.mkdir()
    wanted = ("./opt/local/lib/", "./opt/local/libexec/", "./opt/local/bin/", "./opt/local/share/curl/")
    for pkg in sorted(fetch_macports.OUT.glob("*.tbz2")):
        with tarfile.open(pkg, "r:bz2") as t:
            for m in t.getmembers():
                if not m.name.startswith(wanted) or m.isdir():
                    continue
                target = STAGE / m.name
                if target.exists() or target.is_symlink():
                    target.unlink()  # a newer package version replaces an older one
                t.extract(m, STAGE)
                if target.exists() and not target.is_symlink():
                    target.chmod(target.stat().st_mode | 0o200)
    return STAGE / "opt" / "local"


def assemble(local, leaves):
    shutil.rmtree(OUT, ignore_errors=True)
    for sub in ("bin", "lib", "share"):
        (OUT / sub).mkdir(parents=True)
    by_name = {}
    for leaf, lib in sorted(leaves.items()):
        if by_name.setdefault(lib.name, lib) != lib:
            sys.exit("two different libraries are both named %s" % lib.name)
        if not (OUT / "lib" / lib.name).exists():
            shutil.copyfile(lib, OUT / "lib" / lib.name)
        if leaf != lib.name:
            os.symlink(lib.name, OUT / "lib" / leaf)
    for name in BINARIES:
        shutil.copyfile(real(local / "bin" / name), OUT / "bin" / name)
        (OUT / "bin" / name).chmod(0o755)
    shutil.copyfile(real(local / "share" / "curl" / "curl-ca-bundle.crt"), OUT / "share" / "curl-ca-bundle.crt")
    for name, line in WRAPPERS.items():
        path = OUT / "bin" / name
        path.write_text('#!/bin/sh\nLK="$(cd "$(dirname "$0")/.." && pwd)"\n%s\n' % line)
        path.chmod(0o755)
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file() and not p.is_symlink())
    links = sum(1 for p in (OUT / "lib").iterdir() if p.is_symlink())
    print("assembled %s: %d libraries (+%d symlinks), %.1f MB" % (OUT, len(by_name), links, size / 1e6))
    for name in sorted(by_name):
        print("  %7.0f KB  %s" % ((OUT / "lib" / name).stat().st_size / 1e3, name))


def install():
    tar = subprocess.Popen(["tar", "-czf", "-", "-C", str(TOOLS), "LionKit"], stdout=subprocess.PIPE)
    subprocess.check_call(["ssh", "-o", "BatchMode=yes", HOST,
                           "rm -rf ~/Library/LionKit.new && mkdir ~/Library/LionKit.new && "
                           "tar -xzf - -C ~/Library/LionKit.new 2>/dev/null && "
                           "mv ~/Library/LionKit.new/LionKit/* ~/Library/LionKit.new/ && "
                           "rmdir ~/Library/LionKit.new/LionKit && "
                           "( [ -d ~/Library/LionKit/src ] && mv ~/Library/LionKit/src ~/Library/LionKit.new/ ; true ) && "
                           "rm -rf ~/Library/LionKit && mv ~/Library/LionKit.new ~/Library/LionKit"],
                          stdin=tar.stdout)
    tar.wait()
    print("installed on %s:~/Library/LionKit" % HOST)


def main():
    for port, archive in ROOTS:
        fetch_macports.main(port, archive)
    local = extract()
    assemble(local, closure(local))
    if "--no-install" not in sys.argv:
        install()


if __name__ == "__main__":
    main()
