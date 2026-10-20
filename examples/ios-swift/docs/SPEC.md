# Cat Collector — Spec (excerpt)

> Trimmed from a real app to show the format. A full spec also has product,
> screens, data and release sections; see `templates/SPEC.md`.

## 2. Game rules

### 2.1 XP rewards
- **XP-1:** Each tier pays exactly:

| Tier | XP |
|---|---|
| Common | 10 |
| Uncommon | 25 |
| Rare | 60 |
| Legendary | 150 |

- **XP-2:** When the player relabels a catch, they earn the XP of the scanner's result, not of the breed they picked.
- **XP-3:** XP is stored on each capture and never recalculated.

### 2.2 Levels
- **LVL-1:** Reaching level *n* takes `50 · n · (n − 1)` total XP (100 for level 2, 300 for level 3).
- **LVL-2:** Titles: 1–2 Novice Explorer, 3–4 Cat Spotter, 5+ Whisker Scout.

## 3. Screens

### 3.1 Scanner (`SCAN`)
- **SCAN-1:** Without camera access, the scanner shows "Camera Access Needed" with an **Open Settings** button.
