# Roadmap

LionKit: new, native software for Mac OS X Lion, so a 2010 MacBook Air stays useful in 2026.
Period-correct look and feel (see `docs/design.md`), modern internet underneath (`lionkit`).

**How to use this file.** Each workstream below is a self-contained brief for one agent session.
Read `CLAUDE.md` first, work on a branch named after the workstream, and keep **your own card**
up to date (Status, Done, Next) when you stop. Don't edit other cards.

Status legend: `todo` · `in progress` · `review` (waiting on the user) · `done`

## Where things stand (2026-11-08)

| Piece | Version | State |
|---|---|---|
| LionKit runtime: curl 8 + OpenSSL 3, dwebp, from MacPorts darwin_11 | — | works, 38 MB, untrimmed |
| `lionkit` library: http, keychain, ghost, spotify, markdown, html2md, cocoa, icons | — | works |
| Planchette (Ghost blog editor) | 0.3 | in user testing |
| Kassett (Spotify Connect remote) | 0.2 | in user testing; cassette redesign mocked up |
| WiFiFix (WPA2/WPA3 transition networks) | — | running on the Mac; script in `system/` |
| Dev tooling: deploy, launch (GUI session), shot, build_lionkit | — | works |

## Milestones

1. **Daily driver**: Planchette and Kassett are good enough that the user reaches for
   them instead of a browser tab. (WS-1, WS-2)
2. **Public beta**: anyone with a Lion Mac can download, open and update the apps from the
   website. (WS-5, WS-6)
3. **Social**: a Mastodon + Bluesky client in the spirit of Tweetie. (WS-4)
4. **Little joys**: Dashboard widgets, Wi-Fi fix for everyone, more apps from the backlog. (WS-3, WS-7)

---

## WS-1 · Kassett: the cassette deck
**Status:** todo · **Branch:** `ws/kassett` · **Owns:** `apps/Kassett`, `lionkit/spotify.py`

Turn Kassett from an iTunes-10-style remote into a cassette-deck player with a full library browser.
The visual spec is **`design/kassett/`** (11 screens; see its README). Match it closely.
Also draw a new app icon: a cassette, in the same materials.

- **Now Playing**: cassette deck. Window-wide brushed-aluminium deck, a cassette whose label shows
  the track/artist (handwritten-marker font feel), two reels that turn while playing (the take-up
  reel grows with progress), chunky piano-key transport buttons, VU-style volume, album art as the
  cassette's J-card. Keep the compact mini-player as a View option.
- **Browser** (a second window or an expanding drawer): source list with LIBRARY (Liked Songs,
  Albums, Artists, Podcasts optional), PLAYLISTS (user's playlists), and a search field.
  Content views: playlist/album track lists (iTunes 10 list style, alternating rows, play-on-
  double-click), artist page (header, top tracks, albums grid), search results (sections:
  Tracks, Artists, Albums, Playlists).
- **Up Next**: queue popover from the deck (`GET /me/player/queue`), add-to-queue from any list.
- **Devices**: the AirPlay-style menu exists (0.2); show device type icons in the deck too.
- Cache artwork on disk (`~/Library/Caches/Kassett/`), JPEG only, small sizes (64/300 px).
- Mind the 2 GB of RAM: page long lists (50 at a time), don't keep large images in memory.

API notes: scopes for library/playlists/follow were already requested in 0.2. Spotify restricted
several endpoints for apps created after Nov 2024 (recommendations, related artists, audio
features, featured/category playlists, Spotify-owned editorial playlists, preview URLs); check the
current docs and design around what's available. Playback control needs Premium.

**Done when:** every screen in the mockup exists, is screenshot-verified on the Mac, works
against the user's account (ask them to click through), and memory stays under ~120 MB.

## WS-2 · Planchette 0.4
**Status:** todo · **Branch:** `ws/planchette` · **Owns:** `apps/Planchette`, `lionkit/ghost.py`, `lionkit/markdown.py`, `lionkit/html2md.py`

0.3 addressed: post states, local draft delete, push as draft, slug/excerpt/tags inspector, WebP,
sorting, polish. First, **get the user's feedback on 0.3** and fix what they report. Then:
- Lion full screen (`NSWindowCollectionBehaviorFullScreenPrimary`) with a distraction-free layout.
- Find bar (`textView.setUsesFindBar_(True)`, Lion's `NSTextFinder`).
- Drag & drop and paste images into the editor (import into media, insert Markdown).
- Schedule a post (date picker in the inspector → `status: scheduled`, `published_at`).
- Feature-image focal preview in the inspector; post URL preview with a copy button.
- Round-trip safety: test `html2md` → `markdown.to_html` on every post on the site; anything lossy
  stays inside an HTML card instead of being rewritten.
- Remember window/split positions; restore the last selected post and scroll position.

**Done when:** the user can write, illustrate, schedule and publish a post without opening Ghost Admin.

## WS-3 · Dashboard widgets
**Status:** todo · **Branch:** `ws/widgets` · **Owns:** `widgets/`

Dashboard is disabled on the Mac; the user must re-enable it (`defaults write com.apple.dashboard
mcx-disabled -bool false; killall Dock`; ask them).
- **Weather** in the style of Apple's widget (big temperature, condition art, 6-day strip) using
  Open-Meteo (no key). Dashboard's WebKit can't do modern TLS, so fetch through
  `widget.system("~/Library/LionKit/bin/lk-curl ...")` with `AllowSystem` in Info.plist.
- **Now Playing** mini widget for Spotify (reuse the refresh token from the keychain through a
  tiny Python helper; read-only plus play/pause/next).
- Stretch: Hacker News top 10, a currency converter.

## WS-4 · Murmur (Mastodon + Bluesky)
**Status:** todo · **Branch:** `ws/murmur` · **Owns:** `apps/Murmur`, `lionkit/mastodon.py`, `lionkit/bluesky.py`, `lionkit/oauth.py` (new: a loopback OAuth helper modelled on `spotify.py`'s; don't edit `spotify.py`)

A Tweetie-2-for-Mac-style client: narrow single-column timeline, avatars on the left, a source
bar on the left edge (Home, Mentions, Lists, Search, Profile) per account, compose in a small
floating window. Accounts: any Mastodon instance (OAuth with a 127.0.0.1 redirect, like
`lionkit/spotify.py`; register the app per instance) and Bluesky (AT Protocol; the user types an
**app password** themselves; store the session in the keychain).
- Images: Bluesky CDN can serve JPEG (`@jpeg`); Mastodon may serve WebP/AVIF; convert through LionKit.
- Videos/GIFs: show a poster frame and open in VLC.
- Timelines as a view-based `NSTableView` with variable row heights; cache avatars on disk.
- Unread position per timeline; refresh every 2 minutes while visible; growl-free (Lion has no
  Notification Center; use the Dock badge).

**Done when:** the user can read, post (with an image), reply, boost/repost and like on both networks.

## WS-5 · LionKit platform
**Status:** todo · **Branch:** `ws/lionkit` · **Owns:** `lionkit/http.py`, `lionkit/cocoa.py`, `lionkit/icons.py`, `tools/build_lionkit.py`, `tools/build_app.py`

- **Trim the runtime** to curl's and dwebp's real dependency closure. Lion has no `otool` (it comes
  with Xcode): read the Mach-O load commands with `macholib` (bundled with Lion's Python in
  `Extras/lib/python`) or with `llvm-objdump --macho --dylibs-used` on Linux. Copy symlinks as
  symlinks. Target ≤ 15 MB. Consider `libavif` for AVIF images.
- **Runtime lookup**: `lionkit.http` finds the runtime in the app bundle (`Resources/LionKit`), then
  `~/Library/LionKit`. Same for `lk-dwebp`.
- **Image pipeline**: one disk cache with size limits, WebP/AVIF → PNG/JPEG, thumbnails
  (`lionkit/images.py`, new file; apps adopt it later).

Do this together with WS-6's packaging (same agent): the release build embeds the trimmed runtime.
Change `lionkit/http.py` additively (lookup order only) so app workstreams aren't disturbed.

**Later, after WS-1 and WS-2 merge:** a shared UI kit in `lionkit/ui.py` (glossy pills, source-list
cells with badges, HUD helpers, LCD view, bottom-bar labels, textured toolbar factory) with the
copies moved out of the apps. Not before: it would collide with the app workstreams.

## WS-6 · Distribution & website
**Status:** in progress (repo public, site live at https://xgzepto.github.io/lionkit/) · **Branch:** `ws/distribution` · **Owns:** `site/`, `docs/distribution.md`, `tools/package.sh`, `.github/`

Plan: `docs/distribution.md`. Remaining:
- `tools/package.sh`: release build (no bundled Python binary, first-run copy, embedded runtime),
  DMG with background + Applications alias, zip, checksums into `dist/`.
- `updates.json` on the site + an update check in each app (via WS-5's http).
- Site polish: real screenshots from the Mac (`tools/shot.py`, never with personal photos in view),
  download buttons wired to Releases, a GitHub link once the repo exists. `site/index.html`'s deck is
  generated from `design/kassett/project/Main.dc.html`; regenerate it when the design changes.
- Publishing: `.github/workflows/pages.yml` deploys `site/` once the repo is on GitHub with Pages
  set to "GitHub Actions".
- Ask the user: repo name/visibility, license, and the Spotify public-build approach. **Never
  create the GitHub repo, push, or publish a release without their explicit go-ahead.**

## WS-7 · System fixes
**Status:** todo · **Branch:** `ws/system` · **Owns:** `system/`

- **WiFiFix for everyone**: Lion labels WPA2/WPA3 transition networks "WPA2 Enterprise" and won't
  join them. Turn `system/WiFiFix/wififix.sh` into a small app with a menu-bar status item: pick
  the network, enter the password once (keychain, not a file), see join status. Must run in the
  GUI session.
- A "Lion in 2026" setup guide on the site: Momiji, uBlock Origin, h264ify, which Apple
  services to switch off, Wi-Fi fix, LionKit apps.

---

## Idea backlog (unclaimed)

- **Reeder-style RSS reader** (feeds over modern TLS; Feedbin/FreshRSS sync optional).
- **Podcast player** in the Instacast mould (RSS + downloads + VLC/QTKit playback).
- **YouTube via yt-dlp** → VLC (needs a Python 3 yt-dlp build for darwin_11; check MacPorts).
- **Hacker News / Lobsters reader**.
- **Weather app** (full window, iCal-era materials) if the widget is loved.
- **Calendar sync helper** for Google/iCloud CalDAV through modern TLS.
