# Distribution plan

How someone with a Lion Mac gets these apps, keeps them updated, and how we build releases.
Status: **design**, owned by workstream WS-6 in `ROADMAP.md`.

## Constraints

- **Lion can't reach GitHub by itself.** Safari 6 and the system networking stop at TLS 1.0;
  github.com and github.io require TLS 1.2+. Visitors need a modern browser on the Lion Mac
  (Momiji, a maintained Firefox fork for 10.7+), or must download on another computer and copy the
  file over USB or a network share. The website says this up front, with a Momiji link.
- **Gatekeeper exists on 10.7.5** (default: Mac App Store and identified developers). Our apps are
  unsigned, so the first launch is right-click → **Open** → Open. The site and the README in each
  download show this with a screenshot. (No Developer ID: $99/yr, and Lion's codesign can't use
  today's certificate chain anyway.)
- **Apple's Python binary isn't ours to redistribute.** Each bundle currently contains a copy of
  `Python.app/Contents/MacOS/Python` so the menu bar shows the app's name. Release builds leave it
  out; the launcher copies it from the system on first run (see below).
- **The runtime is ~14.5 MB.** `tools/build_lionkit.py` keeps only the dependency closure of curl
  and dwebp (19 libraries, each stored once, with symlinks for the other install names). It was
  38 MB before the trim.

## What we ship

One download per app: **`Kassett-0.3.dmg`**, a classic Lion disk image with the app, an
alias to /Applications, a background picture telling you to drag one onto the other, and a
"Read Me First" with the right-click → Open step. A `.zip` alongside it for people who prefer that.

Inside the app bundle:

```
Kassett.app/Contents/
  Info.plist
  MacOS/Kassett          # launcher script (below)
  Resources/main.py, lionkit/, AppIcon.icns
  Resources/runtime/           # the trimmed runtime: bin/curl, bin/dwebp, lib/*.dylib, CA bundle
```

The runtime folder is called `runtime`, not `LionKit`, because HFS+ is case-insensitive:
`Resources/LionKit` and the `Resources/lionkit` package would be the same folder.

**Self-contained runtime per app** (not a shared install): each app works on its own, nothing to
install first, nothing to uninstall but the app. `lionkit.http` looks for the runtime in the
bundle first, then `~/Library/LionKit` (dev builds). `lionkit.http.DWEBP` follows the same order.

**First-run launcher**:

```sh
DIR="$(cd "$(dirname "$0")" && pwd)"
SYS=/System/Library/Frameworks/Python.framework/Versions/2.7/Resources/Python.app/Contents/MacOS/Python
[ -x "$DIR/python" ] || cp "$SYS" "$DIR/python" 2>/dev/null   # names the menu bar after the app
[ -x "$DIR/python" ] && PY="$DIR/python" || PY="$SYS"          # read-only location: still works
exec "$PY" "$DIR/../Resources/main.py" "$@" >>"$HOME/Library/Logs/<Exe>.log" 2>&1
```

## Building a release

The Mac is the build machine (it has AppKit for icons, `sips`, `hdiutil`, `ditto`).

```bash
tools/package.sh apps/Kassett      # → dist/Kassett-0.3.dmg and .zip
```

1. Build the bundle on the Mac into a temp dir with `build_app.py --release` (no Python binary,
   embedded trimmed runtime, version from `app.json`).
2. `tools/make_dmg.py` stages the app, a symlink to /Applications, `Read Me First.rtf`, a
   background drawn with AppKit and the app icon as the volume icon, then builds the image with
   `hdiutil` (UDRW, then UDZO). It writes the window layout (`.DS_Store`) itself and makes the
   background's alias with the Alias Manager while the rw image is mounted hidden, so Finder
   never opens a window on the Mac. (Laying it out with AppleScript would put a Finder window
   and a disk icon in front of whoever is using the Mac.)
3. `ditto -c -k --keepParent` for the zip (keeps the bundle and its symlinks intact).
4. Copy both back to `dist/` on Linux, check them against the Mac's SHA-256 sums, and write
   `dist/SHA256SUMS`.
5. Publish to **GitHub Releases** with `gh release create kassett-v0.3 dist/...`
   (tag per app: `<app-id>-v<version>`). Only with the user's go-ahead.

## Updates

No Sparkle: Sparkle's networking would use Lion's TLS 1.0. Instead each app checks
`https://xgzepto.github.io/lionkit/updates.json` through `lionkit.http` at most once a day:

```json
{"kassett": {"version": "0.3", "url": "https://github.com/.../Kassett-0.3.dmg",
                    "notes": "Cassette deck, library browser, device switching"}}
```

If newer, a Lion-style sheet: "Kassett 0.3 is available — you have 0.2", release notes,
**Download** (opens Momiji at the DMG) / **Not Now**. The site publishes `updates.json`.

## The website

Static HTML in `site/`, published by GitHub Pages through `.github/workflows/pages.yml`
(no build step, no frameworks). It renders well in Momiji and modern browsers.

## Spotify caveat

Spotify developer-mode apps work only for **25 allowlisted accounts**, and Spotify grants extended
quota only to organisations. The bundled Client ID therefore works for the user and people they add
in the Spotify dashboard. Public builds need a "Use your own Spotify app…" path: a short guide on the
site (create an app, add the redirect URI `http://127.0.0.1:8888/callback`) plus an Advanced
button in the account sheet that sets the `clientID` default. **Open question for the user.**

## Decided

- The repo is public at https://github.com/XGZepto/lionkit under the MIT license, and the site is
  served from it at https://xgzepto.github.io/lionkit/.

## Still open

- The Spotify public-build approach (above).
