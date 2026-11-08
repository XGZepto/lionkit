# Kassett mockups

The visual spec for workstream WS-1 (`ROADMAP.md`). Eleven screens: the cassette deck, its Up Next
popover and device menu, the mini player, and the library browser (albums, artists, liked songs,
playlist, album, artist, search).

- **View them**: the interactive canvas at https://claude.ai/artifact/2gjXAKNHfYqfoPq3E4zVJP
  (private to the user; ask them for a screenshot if you can't open it), or read the sources here.
- **Sources**: `project/*.dc.html` are plain HTML + inline CSS (Design Component format: `{{holes}}`
  are filled by the small `renderVals()` script at the bottom of each file). `Main.dc.html` is the
  deck; `Browser.dc.html` holds every library view, switched by its `view` prop. Exact colors,
  gradients, sizes and copy are all in the markup; match them in Cocoa.
- `site/index.html` embeds a static copy of the deck, rendered from `Main.dc.html`.

Translating to AppKit: gradients → `NSGradient`, inset/drop shadows → `NSShadow` or stacked
1 px lines, reels → an `NSView` subclass rotated with a timer (or Core Animation layer),
piano keys → custom `NSButton` cells that stay down (`NSPushOnPushOffButton`).
