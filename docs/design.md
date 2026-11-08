# Designing for Lion (2011–2012)

The bar: an app that could have shipped in 2011 next to iTunes 10, Mail 5, Reeder and Tweetie,
and wouldn't look out of place in an Apple Design Award lineup. Not "a modern app on old macOS".
If it looks flat, it's wrong. If it looks like a web page in a window, it's wrong.

## Reference apps

| For | Look at |
|---|---|
| Media / players | iTunes 10.5 (LCD, source list, grid view, AirPlay menu), Rdio desktop, Ecoute |
| Reading / lists | Reeder for Mac (3-pane, unread dots), Mail 5 (Lion's 2-line message list), Sparrow |
| Social | Tweetie 2 for Mac, Tweetbot for Mac (2012): narrow single column, avatars, swipe-free |
| Writing | iA Writer (2011), Byword, Ulysses (2012); Pages for the inspector HUD |
| Skeuomorphism | iCal 5 (leather + torn paper), Address Book (book), Game Center (felt), Find My Friends |
| Tools | Coda 2, Things, Cobook, Pixelmator 2, Kaleidoscope |

## Chrome & materials

- **Textured windows** (`NSTexturedBackgroundWindowMask`) for media/player apps, with a **bottom
  bar** (`setContentBorderThickness_forEdge_`, 22–32 px) holding counts and status in
  **engraved** text (`cell.setBackgroundStyle_(NSBackgroundStyleRaised)`), 11 px.
- **Toolbars**: textured rounded buttons (`NSTexturedRoundedBezelStyle`) with **template images**
  (`lionkit.icons`), 25 px tall; segmented controls `NSSegmentStyleTexturedRounded`. Icon-only is fine
  when tooltips are set.
- **Source lists** (`NSTableViewSelectionHighlightStyleSourceList`) for navigation: ALL-CAPS group
  headers, 16 px icons, counts as gray capsule badges on the right.
- **HUD panels** (`NSHUDWindowMask`) for inspectors over content; **popovers** (`NSPopover`, new in
  Lion) for transient detail; **sheets** for anything modal to a window.
- **Materials** where they mean something: leather + stitching (notebooks, calendars), linen
  (Lion's signature: Mission Control, login), brushed aluminium (hardware-like controls), paper,
  and the iTunes **LCD** (pale green-gray gradient, dark text, inner shadow).
- **Gloss**: capsules and badges get a top-half highlight; buttons and pills a 1 px white
  inner highlight on top and a darker 1 px border. Text on colored chrome gets a 1 px shadow
  (white below on light chrome, black above on dark).
- Rounded corners: 4–6 px for panels, full capsules for pills. Shadows soft and downward.

## Type

- UI: **Lucida Grande** (the system font): 13 px regular for content and controls, 11 px for
  secondary/bars, 9–10 px bold caps for badges and group headers. Helvetica Neue is *not* Lion's UI font.
- Reading/writing: Georgia, Hoefler Text, Baskerville, Palatino. Code: Menlo.
- Headline numbers on LCDs and players: Helvetica Bold, slightly condensed spacing.

## Color

- Lion system blue for selection (`NSColor.alternateSelectedControlColor`); source-list blue-gray
  sidebar (≈ #DCE2E9 → #D1D8E0); window chrome grays from the textured window itself.
- Status colors used across our apps: local/neutral gray #8C8C8C, draft amber #E2961E,
  scheduled blue #3C78CD, published/online green #3CA04B, error/attention orange #D67828.
- Content backgrounds: warm paper #FCF9F1 for writing; white for lists; never pure black.

## Motion

Lion apps animate *a little*: sheet slides, popover fades, 0.2–0.25 s ease-in-out. Use
`NSAnimationContext` + animator proxies. The user loves Lion's animations; don't fight them,
don't overdo them. A spinning cassette reel is fine; a bouncing button is not.

## Icons

512×512 drawn in code in `icon.py` (`render(path, size)` with AppKit). Lion icons are objects
with perspective and material: a leather notebook, a glossy disc, a cassette, a speech bubble
made of glass. Strong silhouette, top-down light, soft drop shadow. No flat glyph-on-a-square.

## Layout on this Mac

The screen is **1440×900**, non-Retina. Default windows ≤ 1240×760; minimum sizes that still
work at 860×460. Respect the menu bar and Dock. Test at the default and minimum sizes.

## Verify

Screenshot every state you touch (`tools/shot.py`), look at it at 100 %, and compare against a
reference app. Check: alignment to a 4 px grid, engraved text where Lion uses it, truncation
(…) instead of clipping, empty states (no blank panes: say what's missing and what to do),
loading states (a small spinner in the bottom bar, not a modal), and error text a human
can act on.
