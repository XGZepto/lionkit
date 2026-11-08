# Working on LionKit

New native software for **Mac OS X Lion 10.7.5**, built from a Linux PC and deployed over SSH to
a real 2010 MacBook Air. Read this file before you change anything; read `ROADMAP.md` to find
your workstream, and `docs/design.md` before you draw a single pixel.

## The machines

| | |
|---|---|
| **Dev box** | Linux (Pop!_OS). The repo lives at `~/Projects/lion-apps`. Python 3 for tooling. |
| **The Mac** | `ssh lionmac` (key auth, already configured). MacBookAir3,2: Core 2 Duo 1.86 GHz, **2 GB RAM**, 1440×900 screen, OS X Lion 10.7.5. |
| **Mac runtime** | System Python **2.7.1** + **PyObjC 2.3.2a0** (both ship with Lion). No Xcode, no compiler, no Homebrew. |
| **LionKit runtime** | `~/Library/LionKit/{bin,lib,share}` on the Mac: MacPorts' signed `darwin_11` curl (OpenSSL 3, TLS 1.3) and `dwebp`, via the `lk-curl` / `lk-dwebp` wrappers. Rebuilt by `tools/build_lionkit.py`. |

**The Mac is a person's daily computer.** Someone may be using it while you work.
- Launch things in the background (`open -g`, or `tools/launch.sh`). Never take focus or switch Spaces.
- Don't quit an app the user has open unless your task needs it; say so in your report when you do.
  Apps keep their state on disk, so a quit-and-relaunch loses nothing.
- Never change system settings. Anything that needs root goes in a script; ask the user to run it
  with `ssh -t lionmac sudo bash <script>`.
- Keep it light: 2 GB of RAM. No background daemons unless the task is one.

## Security rules (non-negotiable)

- Never read, print or use any password or credential file on the Linux box, and never type a real
  account password anywhere. If something needs a password, ask the user to do that step.
- Secrets live in the Mac's login keychain via `lionkit.keychain` (the `/usr/bin/security` CLI).
  Never write tokens to plain files, logs or the repo.
- Don't read files on the Mac that hold Wi-Fi or account passwords.
- Don't commit personal data: no real SSIDs, emails or tokens in code, docs or screenshots.

## The loop

```bash
tools/deploy.sh apps/Kassett            # copy sources to the Mac, syntax-check, build the .app
tools/launch.sh relaunch "Kassett"     # (re)open it in the GUI session, in the background
tools/shot.py "Kassett" /tmp/kassett.png    # capture its window(s) without bringing them forward
ssh lionmac tail -50 ~/Library/Logs/Kassett.log    # stdout/stderr + Python tracebacks
```

Then **look at the screenshot** (Read the PNG) before you call anything done. Every UI change gets
verified this way; compare against the references in `docs/design.md`.

- `tools/launch.sh` goes through the **dev launcher**, a LaunchAgent in the Mac's GUI session, so
  the app can read the unlocked login keychain. Apps opened straight over SSH (`open -g ...`) see the
  keychain as **locked** and look logged out. If `launch.sh` says the launcher isn't running, ask the
  user to run `launchctl load -w ~/Library/LaunchAgents/local.lionkit.devlauncher.plist` in Terminal
  on the Mac (once per login session until they log out and in).
- `SHOT_WINDOWS=3 tools/shot.py ...` captures up to 3 windows (sheets, panels, HUDs).
- You can't click on the Mac. To exercise a state, add a hidden launch argument or a defaults flag
  (e.g. `defaults write page.zepto.kassett DebugOpenView playlist`), or ask the user to click
  through it. Remove debug hooks before merging if they'd confuse a user.
- Deploys build in a private temp dir, so agents in different worktrees can deploy at the same time.
  **Two agents must not build the same app at once**: one workstream per app.

## Writing code for Lion

Python **2.7.1** (no f-strings, no `nonlocal`, `print` needs the `__future__` import, `unicode` vs
`str` matter). Start files with `# -*- coding: utf-8 -*-` and use `u"..."` for UI text. Python's
unicode indices equal NSString's UTF-16 indices on this narrow build.

PyObjC 2.3 gotchas that have bitten us:
- Methods on `NSObject` subclasses become Objective-C selectors: **no `*args`/`**kwargs`**, and
  **call them positionally** (`self.push(None, False, True)`, never `push(status=None, ...)`).
  Plain helpers that shouldn't be selectors can live outside the class.
- Check every Cocoa API against **10.7**. Lots of convenient methods are newer
  (`NSFont.fontWithSize_` is 10.15, `NSStackView` is 10.9, `NSVisualEffectView` 10.10, auto layout
  exists but is painful here; use frames + autoresizing masks). Available and period-correct in
  10.7: `NSPopover`, full-screen windows, `NSTextFinder` find bar, view-based `NSTableView`.
- `NSSplitView` panes need explicit frames after adding subviews (`setFrame_` + `adjustSubviews`).
- `NSOutlineView` items: use `NSMutableDictionary` objects and compare with `==`.
- Keep state as plain Python attributes on the delegate; build UI in code (no nibs).

Networking and media:
- **All HTTPS goes through `lionkit.http`** (curl with modern TLS). Lion's own `urllib2`,
  `NSURLConnection`, WebKit and Safari stop at TLS 1.0 and fail against almost every site today.
- WebKit (`WebView`) can't fetch modern HTTPS images or decode WebP: download through
  `lionkit.http` into a cache and hand WebKit a `file://` URL; convert WebP with `lk-dwebp`
  (see `viewable()` in `apps/Planchette/main.py`).
- Long work goes through `lionkit.cocoa.in_background(work, done)`; `done(result, error)` runs on
  the main thread. Never touch AppKit from a background thread.

## Repo layout

```
lionkit/          shared library (copied into every app bundle at build time)
apps/<App>/       main.py + app.json {name, id, version} + icon.py (draws the icon with AppKit)
widgets/          Dashboard widgets (.wdgt folders)
system/           system-level fixes (Latchkey)
design/           HTML mockups: the visual spec for upcoming UI work
site/             the public website (GitHub Pages, static HTML)
docs/             design guide, distribution plan, notes
tools/            deploy, build, launch, screenshot, runtime (MacPorts) tooling
```

## Git

- One branch per workstream (`ws/kassett`, ...). Small, focused commits.
- Commit with the identity already configured for this repo (the user's GitHub noreply address;
  don't override it with `-c user.email=...`), and end the message with
  `Co-Authored-By: Claude <noreply@anthropic.com>` (use your own model name if you know it).
- The repo is public at https://github.com/XGZepto/lionkit. **Don't push** and don't open PRs:
  the coordinating session merges workstream branches into `master` and pushes.
- When you finish or pause, update your workstream's card in `ROADMAP.md` (status, what's done,
  what's next). Only edit your own card to avoid merge conflicts.
- Bump `version` in the app's `app.json` when you ship a user-visible change.

## Reporting back

End with what changed, the screenshot(s) that prove it, anything you couldn't verify and why,
and what the user needs to do on the Mac (if anything). Be honest about rough edges; the user
cares a lot about polish and will notice.
