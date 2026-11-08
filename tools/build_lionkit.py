#!/usr/bin/env python3
"""Assemble LionKit (modern curl + WebP tools for OS X Lion) from MacPorts' signed darwin_11 builds
and install it on the Mac at ~/Library/LionKit.

usage: tools/build_lionkit.py [--no-install]
"""
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
STAGE = TOOLS / "stage"
OUT = TOOLS / "LionKit"
HOST = os.environ.get("LION_HOST", "lionmac")


def real(path):
    """Resolve symlinks whose targets are absolute /opt/local paths inside the stage dir."""
    for _ in range(20):
        if not path.is_symlink():
            return path
        target = os.readlink(path)
        path = Path(str(STAGE) + target) if target.startswith("/") else path.parent / target
    return path


def main():
    for port, archive in ROOTS:
        fetch_macports.main(port, archive)
    shutil.rmtree(STAGE, ignore_errors=True)
    shutil.rmtree(OUT, ignore_errors=True)
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
    local = STAGE / "opt" / "local"
    for sub in ("bin", "lib", "share"):
        (OUT / sub).mkdir(parents=True)
    for lib in local.glob("lib/*.dylib"):
        shutil.copyfile(real(lib), OUT / "lib" / lib.name)
    for name in BINARIES:
        shutil.copyfile(real(local / "bin" / name), OUT / "bin" / name)
        (OUT / "bin" / name).chmod(0o755)
    shutil.copyfile(real(local / "share" / "curl" / "curl-ca-bundle.crt"), OUT / "share" / "curl-ca-bundle.crt")
    for name, line in WRAPPERS.items():
        path = OUT / "bin" / name
        path.write_text('#!/bin/sh\nLK="$(cd "$(dirname "$0")/.." && pwd)"\n%s\n' % line)
        path.chmod(0o755)
    print("assembled %s (%d libraries)" % (OUT, len(list((OUT / "lib").iterdir()))))

    if "--no-install" not in sys.argv:
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


if __name__ == "__main__":
    main()
