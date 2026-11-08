#!/usr/bin/env python3
"""Fetch a MacPorts binary package for OS X Lion (darwin_11) plus all its dependencies,
verifying each archive's RIPEMD-160 RSA signature against the MacPorts public key."""
import re, subprocess, sys, tarfile, urllib.request
from pathlib import Path

BASE = "https://packages.macports.org"
OUT = Path(__file__).resolve().parent / "pkgs"
PUBKEY = Path(__file__).resolve().parent / "macports-pubkey.pem"

def listing(port):
    html = urllib.request.urlopen(f"{BASE}/{port}/").read().decode()
    return sorted(set(re.findall(r'href="([^"]+\.tbz2)"', html)))

def split_dep(dep):
    # "curl-ca-bundle-8.23.0_1" -> ("curl-ca-bundle", "8.23.0_1")
    m = re.match(r"^(.*?)-(\d[^-]*_\d+)$", dep)
    return m.group(1), m.group(2)

def pick(port, version, files):
    prefix = f"{port}-{version}"
    cands = [f for f in files if f.startswith(prefix) and (".darwin_11.x86_64." in f or ".noarch." in f)]
    # exact version match: next char after prefix must be '+' or '.'
    cands = [f for f in cands if f[len(prefix)] in "+."]
    if not cands:
        # Older dependency versions get pruned; fall back to the newest non-universal Lion build.
        newer = [f for f in files if f.startswith(port + "-") and f.endswith(".darwin_11.x86_64.tbz2")
                 and re.match(rf"^{re.escape(port)}-\d", f)]
        if not newer:
            sys.exit(f"no Lion archive for {port} {version}")
        print(f"note: {port} {version} not available, using {newer[-1]}")
        return newer[-1]
    return cands[0]

def verify(path):
    sig = path.with_name(path.name + ".rmd160")
    r = subprocess.run(["openssl", "dgst", "-ripemd160", "-verify", str(PUBKEY), "-signature", str(sig), str(path)],
                       capture_output=True, text=True)
    return r.stdout.strip() == "Verified OK"

def fetch(port, fname):
    dest = OUT / fname
    if not dest.exists():
        urllib.request.urlretrieve(f"{BASE}/{port}/{fname}", dest)
        urllib.request.urlretrieve(f"{BASE}/{port}/{fname}.rmd160", OUT / (fname + ".rmd160"))
    return dest

def deps(path):
    with tarfile.open(path, "r:bz2") as t:
        contents = t.extractfile("./+CONTENTS").read().decode()
    return re.findall(r"^@pkgdep (\S+)", contents, re.M)

def main(root_port, root_file):
    OUT.mkdir(exist_ok=True)
    queue, seen, result = [(root_port, root_file)], set(), []
    while queue:
        port, fname = queue.pop(0)
        if fname in seen:
            continue
        seen.add(fname)
        path = fetch(port, fname)
        ok = verify(path)
        result.append((fname, path.stat().st_size, ok))
        for d in deps(path):
            p, v = split_dep(d)
            queue.append((p, pick(p, v, listing(p))))
    for fname, size, ok in result:
        print(f"{'OK ' if ok else 'BAD'} {size/1e6:6.2f} MB  {fname}")
    if not all(ok for *_, ok in result):
        sys.exit("signature verification failed")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
