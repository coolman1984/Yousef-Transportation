# Film 1 – ledger (builder ≠ judge)

| Round | Who | Finding | Change | Result |
|---|---|---|---|---|
| 1 | builder | Dry run hung: background tab gives no frames | Separate Chromium per device | Dry run ~50 s |
| 2 | builder | Panel covered the sidebar | `closePanels` skill | fixed |
| 3 | builder | Phone events stamped in UTC; odometers overlapped in history | `cairoIso()`, ordered history generator | fixed |
| 4 | builder | Chip values visible before their step; notch overlapped header | CSS hide, notch moved into bezel | fixed in previews |
| 5 | builder (final) | 10 frames + contact sheet checked: nothing covered, Arabic legible, figures on stamps match read-back | – | accepted |

## Numbers (out/measure.json)
- Duration 95.3 s, 1920x1080, 30 fps.
- Loudness -16.1 LUFS, true peak -2.9 dBFS, LRA 5.3 (music-only: -16.1 / -2.8).
- Figures shown (trip 26-A-00095, 49442 -> 49560, 118 km, 2.09 h, month 14 trips / 871 km) are checked by `cut.mjs`, which refuses to build if they differ from the shoot read-back.
- Frozen-frame detector flags ~38 s: these are deliberate reading holds on real screens (waiting states), not stalls.

## Honest limits
- Not independently reviewed by a second reviewer (owner asked for one shot).
- Staged: studio clock (2-hour drive skipped), test odometer/paper images (labelled), invented company and people.
- Not filmed: the WhatsApp app itself.
