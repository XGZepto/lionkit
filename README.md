# LionKit

I'm building new Mac apps for **Mac OS X Lion 10.7.5** so my mom's 2010 MacBook Air can keep up
with today's internet. They're written in Python 2.7 and PyObjC, which both come with Lion, so
nothing needs Xcode. A bundled copy of curl and OpenSSL 3 handles modern HTTPS, and every window
follows Lion's own look.

| App | What it does |
|---|---|
| Planchette (`apps/Planchette`) | A Markdown editor for blogs that run on Ghost. It keeps a post list in sync in both directions, shows a live preview, and has an inspector for the slug, excerpt, tags and feature image. |
| Kassett (`apps/Kassett`) | A remote for Spotify Connect in the style of iTunes 10, with a menu for moving playback between devices. Its cassette-deck redesign is in `design/kassett/`. |
| WiFiFix (`system/WiFiFix`) | Lets Lion join Wi-Fi networks that offer WPA2 and WPA3 together. Without it, Lion mistakes them for WPA2 Enterprise and won't connect. |
| lionkit (`lionkit/`) | The shared library behind the apps: HTTPS through curl, the keychain, the Ghost and Spotify APIs, Markdown, and Cocoa helpers. |

If you want to help (person or agent), read [`CLAUDE.md`](CLAUDE.md) first and then pick a
workstream in [`ROADMAP.md`](ROADMAP.md). The design guidelines are in [`docs/design.md`](docs/design.md),
the release plan is in [`docs/distribution.md`](docs/distribution.md), and the website lives in `site/`
and is published at https://xgzepto.github.io/lionkit/.

Planchette and Kassett aren't made by or affiliated with the Ghost Foundation or Spotify.
LionKit is released under the MIT license (see `LICENSE`).

## The runtime

Lion's own networking stops at TLS 1.0. `tools/build_lionkit.py` downloads MacPorts' Lion
(`darwin_11`) builds of curl, OpenSSL 3 and libwebp, checks each against MacPorts' signing key
(`tools/macports-pubkey.pem`), and installs them on the Mac at `~/Library/LionKit`.

## Deploying to the Mac

```bash
tools/deploy.sh apps/Planchette              # build one app on the Mac (host: lionmac)
tools/launch.sh relaunch "Planchette"       # open it in the Mac's GUI session
tools/shot.py "Planchette" shot.png         # screenshot its window over SSH
```

App logs go to `~/Library/Logs/<App>.log` on the Mac. Apps opened directly over SSH see the
login keychain as locked; `tools/launch.sh` avoids that through a small LaunchAgent (install it
once with `tools/launch.sh --install`).
