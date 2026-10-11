# UI Lab report — 2026-10-11T09:53

Base: http://127.0.0.1:45747 · CPU throttle ×4 · budgets: ui-budgets/1 (2026-10-08)

| Page | Screen | FCP | LCP | CLS | TBT | INP | p95 frame | FPS | DOM | JS kB | Fits | a11y | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| overview | 1366x768 | 720 | 720 | 0.005 | 192 | 0 | 16.8 | 60 | 376 | 128 | ✓ | 0 | PASS |
| trips | 1366x768 | 708 | 708 | 0.001 | 257 | 0 | 16.8 | 60 | 1033 | 128 | ✓ | 0 | PASS |
| board | 1366x768 | 696 | 696 | 0 | 276 | 0 | 16.8 | 60 | 1692 | 128 | ✓ | 0 | PASS |
| review | 1366x768 | 476 | 476 | 0.001 | 13 | 0 | 16.7 | 60 | 219 | 128 | ✓ | 0 | PASS |
| vehicles | 1366x768 | 540 | 540 | 0.001 | 45 | 0 | 16.7 | 60 | 558 | 128 | ✓ | 0 | PASS |
| drivers | 1366x768 | 532 | 532 | 0.001 | 49 | 0 | 16.7 | 60 | 532 | 128 | ✓ | 0 | PASS |
| people | 1366x768 | 616 | 616 | 0.001 | 194 | 0 | 16.7 | 60 | 1016 | 128 | ✓ | 0 | PASS |
| places | 1366x768 | 516 | 516 | 0 | 33 | 0 | 16.7 | 60 | 231 | 128 | ✓ | 0 | PASS |
| reports | 1366x768 | 520 | 520 | 0.001 | 10 | 0 | 16.7 | 55.1 | 707 | 128 | ✓ | 0 | PASS |
| excel | 1366x768 | 504 | 504 | 0.001 | 29 | 0 | 16.8 | 60 | 259 | 128 | ✓ | 0 | PASS |
| activity | 1366x768 | 500 | 500 | 0.001 | 101 | 0 | 16.8 | 59 | 2025 | 128 | ✓ | 0 | PASS |
| settings | 1366x768 | 580 | 580 | 0.001 | 106 | 0 | 16.7 | 60 | 363 | 128 | ✓ | 0 | PASS |
| help | 1366x768 | 504 | 504 | 0 | 28 | 0 | 16.7 | 60 | 252 | 128 | ✓ | 0 | PASS |
| overview | 390x844 | 620 | 708 | 0.002 | 110 | 0 | 16.7 | 60 | 376 | 128 | ✓ | 0 | PASS |
| trips | 390x844 | 644 | 644 | 0.001 | 183 | 0 | 16.8 | 60 | 1033 | 128 | ✓ | 0 | PASS |
| board | 390x844 | 740 | 740 | 0.001 | 164 | 0 | 16.8 | 59.5 | 1692 | 128 | ✓ | 0 | PASS |
| review | 390x844 | 472 | 556 | 0.001 | 7 | 0 | 16.7 | 60 | 219 | 128 | ✓ | 0 | PASS |
| vehicles | 390x844 | 528 | 528 | 0.001 | 60 | 0 | 16.7 | 60 | 558 | 128 | ✓ | 0 | PASS |
| drivers | 390x844 | 516 | 516 | 0.001 | 41 | 0 | 16.8 | 60 | 532 | 128 | ✓ | 0 | PASS |
| people | 390x844 | 620 | 620 | 0.001 | 176 | 0 | 16.7 | 60 | 1016 | 128 | ✓ | 0 | PASS |
| places | 390x844 | 476 | 476 | 0.001 | 21 | 0 | 16.7 | 60 | 231 | 128 | ✓ | 0 | PASS |
| reports | 390x844 | 496 | 580 | 0.001 | 15 | 0 | 16.8 | 57.1 | 707 | 128 | ✓ | 0 | PASS |
| excel | 390x844 | 504 | 504 | 0.005 | 21 | 0 | 16.8 | 60 | 259 | 128 | ✓ | 0 | PASS |
| activity | 390x844 | 468 | 468 | 0.001 | 119 | 0 | 16.7 | 60 | 2025 | 128 | ✓ | 0 | PASS |
| settings | 390x844 | 576 | 576 | 0.001 | 96 | 0 | 16.8 | 60 | 363 | 128 | ✓ | 0 | PASS |
| help | 390x844 | 792 | 792 | 0.001 | 38 | 0 | 16.8 | 60 | 252 | 128 | ✓ | 0 | PASS |

Largest JS transfer of one page: 128 kB (budget 300 kB).

## Accessibility findings

- overview 1366x768: heading-order(moderate,1)
- review 1366x768: heading-order(moderate,1)
- places 1366x768: heading-order(moderate,1)
- reports 1366x768: heading-order(moderate,1)
- excel 1366x768: heading-order(moderate,1)
- settings 1366x768: heading-order(moderate,1)
- overview 390x844: heading-order(moderate,1)
- review 390x844: heading-order(moderate,1)
- places 390x844: heading-order(moderate,1)
- reports 390x844: heading-order(moderate,1)
- excel 390x844: heading-order(moderate,1)
- settings 390x844: heading-order(moderate,1)
