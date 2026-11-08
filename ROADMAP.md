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
| LionKit runtime: curl 8 + OpenSSL 3, dwebp, from MacPorts darwin_11 | — | works, trimmed to 14.5 MB |
| `lionkit` library: http, keychain, ghost, spotify, markdown, html2md, cocoa, icons | — | works |
| Planchette (Ghost blog editor) | 0.3 | in user testing |
| Kassett (Spotify Connect remote) | 0.2 | in user testing; cassette redesign mocked up |
| Latchkey (WPA2/WPA3 transition networks) | 0.1 | in daily use on the Mac: joined ZipZap with its saved password, opens at login |
| Dev tooling: deploy, launch (GUI session), shot, build_lionkit | — | works |

## Milestones

1. **Daily driver**: Planchette and Kassett are good enough that the user reaches for
   them instead of a browser tab. (WS-1, WS-2)
2. **Public beta**: anyone with a Lion Mac can download, open and update the apps from the
   website. (WS-5, WS-6)
3. **Social**: a Mastodon + Bluesky client in the spirit of Tweetie. (WS-4)
4. **Little joys**: Dashboard widgets, Latchkey for everyone, more apps from the backlog. (WS-3, WS-7)

## Current milestone: public beta 0.5

The goal is a first public beta. Someone with a Lion Mac can go to the website, download Kassett
and Planchette from a GitHub release, open them, and get told when a newer version is out. The
milestone is reached when all of these are true:

- [ ] Kassett has the library browser from the mockups (Liked Songs, albums, artists, playlists,
      album and artist pages, search), and people outside the 25 allowlisted Spotify accounts can
      use their own Spotify app when login fails. (WS-1)
- [ ] Planchette 0.4 is finished, including the bug where a two-line title hides the first line of
      text under the divider. (WS-2)
- [ ] Both apps check `updates.json` on the website once a day and offer new versions from a menu
      item and a sheet. (WS-6)
- [ ] The DMGs have been looked at in Finder, the right-click Open path works on a downloaded copy,
      and the site has download buttons pointing at the release. (WS-6)
- [ ] The coordinating session has merged everything, tested it on the Mac, and published the
      release as a GitHub pre-release.

---

## WS-1 · Kassett: the cassette deck
**Status:** in progress (parked 2026-11-08) · **Branch:** `ws/kassett` · **Owns:** `apps/Kassett`, `lionkit/spotify.py`

**Done (on `ws/kassett`, deployed to the Mac):** the cassette deck is built and screenshot-verified, including
against the user's real account. It has turning reels that spin by pack size, packs that grow by area,
latching keys, a rolling tape counter, a knob that changes volume by drag or scroll, a seekable progress bar and
J-card art from the disk cache. Seeking and skipping whirr the reels. The window uses 61 MB of memory. The Up
Next popover is verified with fake data, and the cassette color can be changed under View. The device menu now
has a "Play On" header, device-type icons and a "busy" note. The mini player and a Controls menu with shortcuts
are written. `lionkit/spotify.py` has the library, catalog, queue and `/me/library` calls, follows Spotify's
February 2026 Development Mode rules, and re-reads the keychain token before refreshing (for the WS-3 widget).
Code: `main.py`, `deck.py`, `upnext.py`, `paint.py`, `glyphs.py`, `art.py`.

**Next:** I still need to write `apps/Kassett/library.py`, the library browser. Until then the LIBRARY key and
View > Show Library show a "not in this build yet" message. The plan for it is a source list, iTunes-style
track lists with right-click Add to Up Next, album and artist grids, and the artist and search views. Because
of the 2026 changes, the artist page's Popular list comes from an `artist:` search, followed playlists can be
played but not listed, and search returns at most 10 results per type. After that, I need to check the mini
player on screen (its capture came back empty), draw the cassette app icon in `icon.py`, bump the version to
0.3, and ask the user to click through the devices menu, the transport keys and the Up Next popover with real
playback. `user-follow-modify` was added, so the user should log out and in once to follow artists from Kassett.
Debug hooks: `defaults write page.zepto.kassett DebugFakeState -bool yes` shows a fake song, and `DebugOpenView`
opens `mini`, `upnext` or `library:<view>` at launch.

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
**Status:** done · **Branch:** `ws/planchette` · **Owns:** `apps/Planchette`, `lionkit/ghost.py`, `lionkit/markdown.py`, `lionkit/html2md.py`

0.4 adds Lion full screen (the post list steps aside, the toolbar auto-hides), the find bar,
images by drag and drop or paste, scheduling and moving publish dates from the inspector, a post
address with Copy, a feature-image well that crops like a post card, remembered panes and per-post
scroll positions, and a header that scrolls with the text. The post list and status line say a
post's state once, through its group and one plain line.

Round trips are safe: `html2md` renders every block back and keeps anything that wouldn't come
back the same as an HTML card; line breaks, Ghost-style quotes, captions with quotes and image
sizes survive. On the 12 posts on the site the result is identical, with one block kept as a card.

Ideas for later: fold HTML cards into a compact token in the editor; keep a link's `rel` in
Markdown; a Ghost-style slug preview for non-Latin titles.

**Done when:** the user can write, illustrate, schedule and publish a post without opening Ghost Admin.

## WS-3 · Dashboard widgets
**Status:** review (Forecast is waiting on the user's look in Dashboard; Now Playing is parked) · **Branch:** `ws/widgets` · **Owns:** `widgets/`, `tools/widget_preview.py`

- **Weather** in the style of Apple's widget (big temperature, condition art, 6-day strip) using
  Open-Meteo (no key). Dashboard's WebKit can't do modern TLS, so fetch through
  `widget.system("~/Library/LionKit/bin/lk-curl ...")` with `AllowSystem` in Info.plist.
- **Now Playing** mini widget for Spotify (reuse the refresh token from the keychain through a
  tiny Python helper; read-only plus play/pause/next).
- Stretch: Hacker News top 10, a currency converter.

Done (2026-11-08):
- `widgets/Forecast.wdgt` 0.1 is Lion's Weather reimagined on Open-Meteo. It has a slate panel by
  day and plum by night, canvas-drawn condition art (the moon shows its real phase), a six-day strip
  that folds away on click, and a linen back with city search, °C/°F and Apple's info and Done
  buttons. The last forecast is cached in the widget's prefs so Dashboard never opens to a blank.
- `tools/widget_preview.py` renders a widget in Lion's WebKit off screen over SSH, with a stand-in
  `widget` object, and saves PNGs of any state (`--eval`, `--shot`). Every state above was checked this way.
- On the Mac, Dashboard is re-enabled (the user approved it) and Forecast is added to the layer
  at (980, 560). Hong Kong is preset as the default place with `defaults write
  widget-page.zepto.widget.forecast place '{...}'`. The old Dashboard prefs are backed up in
  `~/Library/LionKitDev/com.apple.dashboard.plist.backup`.

Next:
- Get the user's screenshot of Forecast in Dashboard. Check the close-box position
  (`CloseBoxInsetX/Y` 9/41), the flip, the fold animation and the window resizes, none of which the
  preview can show. Ask whether Apple's broken Weather widget should come out of the layer.
- **Now Playing** (not started): follow Kassett's mini player (`design/kassett/project/Mini.dc.html`),
  with an aluminium bar, a small cassette whose reels turn while playing, the title in Marker Felt
  and the artist in Noteworthy (both ship with Lion), and prev/play/next buttons. Clicking the cassette
  opens Kassett. A `/usr/bin/python -S` helper in the bundle prints JSON for
  `status|play|pause|next|previous`. It finds the client ID from `defaults read page.zepto.kassett
  clientID` (or the keychain item's account), reads the refresh token from "LionKit Spotify" right
  before refreshing, writes a rotated token back with `security -i add-generic-password -U`,
  caches the access token in a second item ("LionKit Spotify Widget"), and serializes refreshes
  with a `flock`. Tokens go through a 0600 header file, never argv. Spotify revokes a refresh token
  once it's been exchanged, so this depends on WS-1 making `lionkit/spotify.py` re-read the keychain
  before each refresh. That request was sent to the Kassett session on 2026-11-08.

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
**Status:** in progress (runtime done) · **Branch:** `ws/distribution` (runtime part, with WS-6) · **Owns:** `lionkit/http.py`, `lionkit/cocoa.py`, `lionkit/icons.py`, `tools/build_lionkit.py`, `tools/build_app.py`

- ~~Trim the runtime~~ **done**: 14.5 MB (was 38), 19 libraries stored once plus 5 symlinks. The load
  commands are read on the Mac with Lion's macholib (this Linux box has no llvm-objdump), so
  `build_lionkit.py` needs the Mac even with `--no-install`. Installed as the dev runtime too.
  Still open: consider `libavif` for AVIF images.
- ~~Runtime lookup~~ **done**: `lionkit.http` uses `Contents/Resources/runtime` in the bundle, then
  `~/Library/LionKit`; `http.DWEBP` follows it (Planchette uses it now: a one-line change in WS-2's
  file). Not `Resources/LionKit`: HFS+ is case-insensitive, so it would merge with `lionkit/`.
- **Next (runtime)**: launched from a read-only place (the DMG), an app runs under the system
  binary and its icon is Python's rocket (Kassett's art placeholder shows it). `cocoa.py` could set
  `NSApp.setApplicationIconImage_` from `AppIcon.icns`. IDN hostnames need a UTF-8 locale for
  curl; GUI apps may not have one (true before the trim too).
- **Image pipeline**: one disk cache with size limits, WebP/AVIF → PNG/JPEG, thumbnails
  (`lionkit/images.py`, new file; apps adopt it later).

Do this together with WS-6's packaging (same agent): the release build embeds the trimmed runtime.
Change `lionkit/http.py` additively (lookup order only) so app workstreams aren't disturbed.

**Later, after WS-1 and WS-2 merge:** a shared UI kit in `lionkit/ui.py` (glossy pills, source-list
cells with badges, HUD helpers, LCD view, bottom-bar labels, textured toolbar factory) with the
copies moved out of the apps. Not before: it would collide with the app workstreams.

## WS-6 · Distribution & website
**Status:** in progress (repo public, site live at https://xgzepto.github.io/lionkit/, packaging works) · **Branch:** `ws/distribution` · **Owns:** `site/`, `docs/distribution.md`, `tools/package.sh`, `.github/`

Plan: `docs/distribution.md`.
- ~~`tools/package.sh`~~ **done**: `tools/package.sh apps/Kassett apps/Planchette` builds
  `dist/<App>-<version>.dmg` (~6.3 MB) and `.zip` (~6.1 MB) plus `SHA256SUMS`. `build_app.py
  --release` leaves Apple's binary out (the launcher copies it on first run and falls back to the
  system one when the bundle is read-only). `tools/make_dmg.py` writes the window layout itself, so
  Finder never opens a window. Tested from a temp folder on the Mac (zip and DMG copies, a fresh
  sandboxed home): both apps launch in the background, name themselves correctly, log nothing and
  quit cleanly; the read-only fallback runs as "Python".
- **Not verified yet**: how Finder actually draws the DMG window (the `.DS_Store` parses and the
  background alias resolves on the compressed image, but nobody has looked at the window), the
  Gatekeeper right-click → Open path on a quarantined download, and the screenshot for the Read Me.
  The Read Me also doesn't mention Spotify's 25-account limit yet (open question below).
Remaining:
- `updates.json` on the site + an update check in each app (via WS-5's http).
- Site polish: real screenshots from the Mac (`tools/shot.py`, never with personal photos in view),
  download buttons wired to Releases. `site/index.html`'s deck is
  generated from `design/kassett/project/Main.dc.html`; regenerate it when the design changes.
- Publishing: `.github/workflows/pages.yml` deploys `site/` once the repo is on GitHub with Pages
  set to "GitHub Actions".
- Ask the user: repo name/visibility, license, and the Spotify public-build approach. **Never
  create the GitHub repo, push, or publish a release without their explicit go-ahead.**

## WS-7 · System fixes
**Status:** review (Latchkey 0.1 built, not yet tried on a real network) · **Branch:** `ws/system` · **Owns:** `system/`

- **Latchkey for everyone**: Lion labels WPA2/WPA3 transition networks "WPA2 Enterprise" and won't
  join them. Latchkey is a small app with a menu-bar status item: pick the network, enter the
  password once (kept in the keychain), see join status. Must run in the GUI session.
- A "Lion in 2026" setup guide on the site: Momiji, uBlock Origin, h264ify, which Apple
  services to switch off, and the LionKit apps.

Done (0.1, see `system/Latchkey/README.md`): the menu bar app with a key-shaped status glyph
(signal, joining animation, off), a Lion-style network menu, a join dialog modelled on Lion's
own, rejoin with back-off, passwords in the login keychain, Open at Login and Forget.
A brass-key app icon. Demo mode with made-up networks
for screenshots. `tools/deploy.sh` now builds `system/*` apps, and `tools/build_app.py` accepts
extra Info.plist keys (`"info"` in app.json, used for `LSUIElement`).

Verified on the Mac, in demo mode only: every dialog state, the custom menu rows, the status
glyph in the menu bar, and the rejoin loop up to a failed join. The app is installed in
/Applications but not running.

Next:
- Nobody has opened the real menu yet. An open menu can't be captured over SSH, so the user
  needs to click it once (check row highlight, the scan on open, and how the menu resizes).
- "Open at Login" is untested (it adds a real login item). Reading the list works.

---

## Idea backlog (unclaimed)

- **Reeder-style RSS reader** (feeds over modern TLS; Feedbin/FreshRSS sync optional).
- **Podcast player** in the Instacast mould (RSS + downloads + VLC/QTKit playback).
- **YouTube via yt-dlp** → VLC (needs a Python 3 yt-dlp build for darwin_11; check MacPorts).
- **Hacker News / Lobsters reader**.
- **Weather app** (full window, iCal-era materials) if the widget is loved.
- **Calendar sync helper** for Google/iCloud CalDAV through modern TLS.
