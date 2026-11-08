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
| WiFiFix (WPA2/WPA3 transition networks) | 0.1 | menu bar app built (demo-verified); the old script still runs the Mac |
| Dev tooling: deploy, launch (GUI session), shot, build_lionkit | — | works |

## Milestones

1. **Daily driver**: Planchette and Kassett are good enough that the user reaches for
   them instead of a browser tab. (WS-1, WS-2)
2. **Public beta**: anyone with a Lion Mac can download, open and update the apps from the
   website. (WS-5, WS-6)
3. **Social**: a Mastodon + Bluesky client in the spirit of Tweetie. (WS-4)
4. **Little joys**: Dashboard widgets, Wi-Fi fix for everyone, more apps from the backlog. (WS-3, WS-7)

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
**Status:** review (0.5, waiting on the user) · **Branch:** `ws/kassett` · **Owns:** `apps/Kassett`, `lionkit/spotify.py`

**Done:** The cassette deck, mini player, Up Next popover, device menu and Controls menu shipped earlier (see
git history). In 0.5 I added the library browser (`library.py`). It has a source list with Liked Songs,
Albums, Artists and the user's playlists, iTunes-style track lists, album and artist grids, album and
playlist pages, the artist page and search. Lists load 50 rows at a time, and right-clicking a song offers
Play, Add to Up Next, Go to Album, Go to Artist and Add to (or Remove from) Liked Songs. I checked every view
against the mockups with sample data (`fakeclient.py`). Liked Songs and the playlists also loaded from the
user's real account, and the app stayed under 70 MB. When Spotify refuses an account that isn't on the
allowlist, Kassett logs it out and shows a sheet (`ownapp.py`) that explains why. Its "Use My Own Spotify
App…" button expands the sheet into a three-step guide with the redirect URI and a Client ID field that saves
the `clientID` default and logs in again. Preferences still only has Log In and Log Out. The version is 0.5.

**Notes:** Spotify's February 2026 limits shape a few things. The artist page's Popular list comes from an
`artist:` search, followed playlists can be played but not listed, and search shows at most 10 results per
type. The Mac's screen was locked for most of this session, so I added a hidden `DebugSnapshot` setting that
makes Kassett draw its own windows into PNGs. `DebugFakeState` shows a fake song and the sample library, and
`DebugOpenView` opens `mini`, `upnext`, `ownapp`, `ownapp-guide` or `library:<view>` at launch.

**Controls:** The user reported that no controls worked. A hidden probe (`DebugProbe`) showed the cause. They
were playing on a speaker group ("Dining Room + 2"), which Spotify marks `is_restricted`. Spotify answers
every Web API command for a restricted device with 403 "Restricted device" and leaves it out of
`/me/player/devices`. Kassett can't change that. It now dims the keys, knob and progress bar, says in the
bottom bar that only the Spotify app can control the device, and lists the device in the AirPlay menu with
"Spotify app only". Command errors now go to the log.

**Player and library redesign:** After the user shared references (a Sony Walkman, the Duo-Man concept,
an iPhone 4 cassette app and Cassoflow), I rebuilt Now Playing as a Walkman-style player. It has a brushed
blue body, a chrome nameplate, four glossy keys on a silver strip, a volume wheel and an iTunes LCD. The
cassette is drawn to IEC 60094 scale. Reels turn at tape speed divided by pack radius, the tape runs round
the rollers and pins past the pressure pad, and the head and pinch roller move in on play and back on pause.
In the library, albums are cassette cases with printed J-cards standing on walnut shelves, and playlists
and Liked Songs are hand-labelled mixtapes. Views crossfade in 0.2 s between two snapshots, which keeps
the Core 2 Duo smooth. I checked all of this with sample data and with the user's library of 143 albums.

**Polish pass:** The reels are now Core Animation layers, so a playing song costs 6 to 10 percent of a CPU
core instead of about 50. Opening an album from the shelf, an artist page or search flips the pane over in
3D like a Dashboard widget, and going back flips it the other way. The app icon is now the cassette, the mini
player uses the Walkman materials, and the chrome nameplate reads better. A real-data run caught "Invalid
limit" on artist pages: Spotify now allows at most 10 albums per request there. Hidden test settings:
`DebugAnimationScale` slows the flip, and `DebugSnapshot` makes Kassett draw its windows into PNGs.

**Next:** The user should click through playing from a list, Add to Up Next, the devices menu, the keys and
the knob with real playback, and log out and in once so Kassett can follow artists. I haven't drawn the
cassette app icon in `icon.py` yet. I also couldn't test the not-allowlisted sheet with a real refused
account, only through the debug hook.

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
**Status:** in progress (parked 2026-11-08) · **Branch:** `ws/planchette` · **Owns:** `apps/Planchette`, `lionkit/ghost.py`, `lionkit/markdown.py`, `lionkit/html2md.py`

Done on the branch (deployed to the Mac as 0.4, screenshot-checked unless noted):
- Long titles wrap and the header grows; Return or Tab in the title moves into the text. The post's
  path in the status line truncates in the middle instead of being clipped.
- Converter version stored in each pulled post (`html2md.VERSION`); older clean copies re-pull.
- Find bar (`setUsesFindBar_`) with Edit ▸ Find and Spelling and Grammar menus. *Find bar itself not
  screenshotted yet.*
- Lion full screen (View ▸ Enter Full Screen, ⌃⌘F): hides the post list, preview and inspector; the
  toolbar auto-hides. *Not tried on the Mac: entering full screen would switch the user's Space.*
- View ▸ Hide Post List (⌥⌘S). Sidebar width, preview split, preview/post list/inspector visibility,
  and each post's scroll position and selection are remembered.
- Drag and drop or paste images (files or picture data) into the editor → `media:` image lines,
  uploaded on save. Paste was tested through a private pasteboard; real drags need the user.
- Inspector: post address with a Copy button, Publish Date (schedule a draft, move a scheduled or
  published post), feature image cropped like a post card that also takes drops, HUD-style buttons.
  Publish… becomes Schedule…/Unschedule…; the site gets `status: scheduled` + `published_at`.
  *Scheduling hasn't been run against the real site; ask before testing it there.*
- Code and HTML-card shading has no gaps between lines; dates show in the Mac's time zone.
- Hidden `DebugActions` default (see `runDebugActions_`) for screenshotting states over SSH.

Next:
- Ask the user to try full screen, a real drag from Finder, a pasted screenshot, the find bar, and
  (with their go-ahead, on a throwaway draft) Schedule… → Unschedule….
- Round-trip safety: compare `html2md` → `markdown.to_html` on every post (read-only, from inside the
  app because the key needs the GUI keychain), and keep lossy blocks inside an HTML card. Watch image
  cards with `kg-width-wide/full`, width/height and srcset.
- Address preview for posts without a slug; maybe fold HTML cards into a compact token in the editor.

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
**Status:** review (WiFiFix 0.1 built, not yet tried on a real network) · **Branch:** `ws/system` · **Owns:** `system/`

- **WiFiFix for everyone**: Lion labels WPA2/WPA3 transition networks "WPA2 Enterprise" and won't
  join them. Turn `system/WiFiFix/wififix.sh` into a small app with a menu-bar status item: pick
  the network, enter the password once (keychain, not a file), see join status. Must run in the
  GUI session.
- A "Lion in 2026" setup guide on the site: Momiji, uBlock Origin, h264ify, which Apple
  services to switch off, Wi-Fi fix, LionKit apps.

Done (0.1, see `system/WiFiFix/README.md`): the menu bar app with a key-shaped status glyph
(signal, joining animation, off), a Lion-style network menu, a join dialog modelled on Lion's
own, rejoin with back-off, passwords in the login keychain, Open at Login, Forget, "Rejoin Now",
and a guided removal of the old helper. A brass-key app icon. Demo mode with made-up networks
for screenshots. `tools/deploy.sh` now builds `system/*` apps, and `tools/build_app.py` accepts
extra Info.plist keys (`"info"` in app.json, used for `LSUIElement`).

Verified on the Mac, in demo mode only: every dialog state, the custom menu rows, the status
glyph in the menu bar, and the rejoin loop up to a failed join. The app is installed in
/Applications but not running, and the old `local.wififix` agent is untouched.

Next:
- Nobody has opened the real menu yet. An open menu can't be captured over SSH, so the user
  needs to click it once (check row highlight, the scan on open, and how the menu resizes).
- Joining for real is untested: the join code is the script's, but the real scan and the
  join run only when the user acts. The user does the migration in the README's order.
- "Open at Login" is untested (it adds a real login item). Reading the list works.
- The site's Wi-Fi Fix card still shows the old glass-disc icon (WS-6).

---

## Idea backlog (unclaimed)

- **Reeder-style RSS reader** (feeds over modern TLS; Feedbin/FreshRSS sync optional).
- **Podcast player** in the Instacast mould (RSS + downloads + VLC/QTKit playback).
- **YouTube via yt-dlp** → VLC (needs a Python 3 yt-dlp build for darwin_11; check MacPorts).
- **Hacker News / Lobsters reader**.
- **Weather app** (full window, iCal-era materials) if the widget is loved.
- **Calendar sync helper** for Google/iCloud CalDAV through modern TLS.
