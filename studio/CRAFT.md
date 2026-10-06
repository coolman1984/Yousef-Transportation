<!-- first-sale-contract: 2026-10-06 -->
> **Owner decision — 6 October 2026:** Read [the first-sale contract](../LAUNCH_SCOPE.md) before using this document. The limited pilot core and its launch gates take priority; extra features belong to later releases or separately accepted add-ons. Existing implementation/history below is preserved and is not a claim of first-sale acceptance.

# Craft notes
- One real shoot per device, each in its own Chromium started with `--force-device-scale-factor` (office 1.5, phone 2).
  Without that flag the screencast sends CSS-size frames; `cut.mjs` now refuses such a take.
- The page cursor is hidden while shooting; the stage logs the hand's path and the composer draws cursor, click ripple and finger taps.
- Everything on screen is proven by an API read-back; the composer only lays out, never invents numbers.
- Camera: `cut.mjs` bakes one track per device (fx, fy, zoom): follow shots push in (office <= 1.4x, phone <= 1.16x) and glide between actions,
  looks frame a box, everything else is the wide shot; gaussian smoothing (0.55 s) gives ease-in/out and a little anticipation.
- Speed ramps: idle stretches (no event, no new frame) play up to 2.6x; readings after a proven result stay at 1x.
- Render: 60 fps, lossless PNG frames, three parallel slices joined without re-encoding; master CRF 14; a two-pass copy (~27 MB) for chat.
- One command: `node make.mjs` (add `--skip-shoot` to re-cut and re-render from the last take).
