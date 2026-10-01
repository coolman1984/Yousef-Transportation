# Film 1 – ledger (builder ≠ judge)

| Round | Who | Finding | Change | Result |
|---|---|---|---|---|
| 1 | builder | Dry run hung: background tab gives no frames | Separate Chromium per device | Dry run ~50 s |
| 2 | builder | Panel covered the sidebar | `closePanels` skill | fixed |
| 3 | builder | Phone events stamped in UTC; odometers overlapped in history | `cairoIso()`, ordered history generator | fixed |
| 4 | builder | Chip values visible before their step; notch overlapped header | CSS hide, notch moved into bezel | fixed in previews |
| 5 | builder | v1 accepted (95 s, still wide camera) | – | delivered |
| 6 | **owner** | "Quality of everything is very bad; I want a professional, cinematic film with light zoom in/out" | v2 (below) | – |
| 7 | builder | Raw frames were 1280x800 although the page ran at 1.5x: the screencast ignores the emulated scale | `--force-device-scale-factor`; `cut.mjs` refuses CSS-size frames | 1920x1200 / 786x1702 frames |
| 8 | builder | 2x/3x shoot ran twice as slow (typing 0.65 s per letter) | time-based hand and typing; scale = what the zoom needs | normal speed (88 s take) |
| 9 | builder | Camera pumped in/out per click; phone zoom cropped the shutter | follow shots, gap fill, phone max 1.16x | previews checked |
| 10 | builder (final v2) | 12 frames of the chat copy + a 1:1 crop checked: text sharp, cursor sharp, nothing covered | – | delivered |

## Numbers (out/measure.json, v2)
v2: 92.2 s, 1920x1080, 60 fps. Loudness -15.8 LUFS, true peak -1.5 dBFS, frozen picture 0 s (the camera always breathes).
Master ~135 MB (CRF 14); chat copy 27 MB (two-pass ~2.1 Mbit/s). Figures shown (trip 26-A-00095, 49442 -> 49560, 118 km,
month 14 trips / 871 km) are checked by `cut.mjs`, which refuses to build if they differ from the shoot read-back.

## Honest limits
- Not independently reviewed by a second reviewer.
- Staged: studio clock (2-hour drive skipped), test odometer/paper images (labelled), invented company and people.
- Not filmed: the WhatsApp app itself.
