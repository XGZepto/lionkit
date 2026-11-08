#!/bin/sh
# Build the release downloads on the Lion Mac: dist/<App>-<version>.dmg and .zip, plus SHA-256 sums.
# usage: tools/package.sh apps/Kassett [apps/Planchette ...]
#
# Assembles the trimmed runtime (tools/build_lionkit.py --no-install), then builds each app with
# build_app.py --release and packs it with make_dmg.py in a private temp dir on the Mac. Nothing is
# installed, registered with LaunchServices or published, and Finder never opens a window.
set -e
cd "$(dirname "$0")/.."
HOST=${LION_HOST:-lionmac}
[ $# -gt 0 ] || { echo "usage: $0 apps/<App> [apps/<App> ...]" >&2; exit 2; }
for t in "$@"; do
    [ -f "${t%/}/app.json" ] || { echo "no app.json in $t" >&2; exit 2; }
done

log=$(mktemp)
python3 tools/build_lionkit.py --no-install >"$log" 2>&1 || { cat "$log" >&2; rm -f "$log"; exit 1; }
grep '^assembled' "$log" | sed "s#$PWD/##"
rm -f "$log"

WORK=$(ssh -o BatchMode=yes "$HOST" 'mktemp -d /tmp/lionkit-release.XXXXXX')
trap 'ssh -o BatchMode=yes "$HOST" "rm -rf $WORK"' EXIT
tar --exclude='*.pyc' --exclude='__pycache__' -czf - lionkit apps tools/build_app.py tools/make_dmg.py tools/LionKit |
    ssh -o BatchMode=yes "$HOST" "tar -xzf - -C $WORK 2>/dev/null"

mkdir -p dist
for t in "$@"; do
    t=${t%/}
    name=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["name"])' "$t/app.json")
    ssh -o BatchMode=yes "$HOST" "cd $WORK && /usr/bin/python tools/build_app.py --release '$t' build >/dev/null &&
        /usr/bin/python tools/make_dmg.py 'build/$name.app' out"
done
scp -q -o BatchMode=yes "$HOST:$WORK/out/*" dist/
ssh -o BatchMode=yes "$HOST" "cd $WORK/out && LC_ALL=C shasum -a 256 *" | (cd dist && sha256sum -c --quiet -) ||
    { echo "the copies in dist/ don't match the ones built on the Mac" >&2; exit 1; }
(cd dist && sha256sum -- *.dmg *.zip >SHA256SUMS && cat SHA256SUMS)
ls -l dist
