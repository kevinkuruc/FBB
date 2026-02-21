# Draft Tool Audit Report

## Executive Summary

**The core HTML draft tool (`draft_tool.html`) is mathematically sound and the data pipeline is correct.** The win-probability-based marginal value approach is well-designed for H2H category leagues. The data flows from raw projections through normalization to final player arrays without errors.

Since the last audit, several improvements were made: the PA floor was raised from 600 to 625, SDs and averages now use a 34/66 weighted blend of 2024 and 2025 league data, replacement OBP was updated to the actual cohort average (0.324), keepers were temporarily cleared for testing, and the merge conflict in AI_HANDOFF.md was resolved. **All of these changes are correctly implemented in the HTML tool.**

The remaining issues are the same low-priority ones from before: the Python CLI tool is still out of sync, the documentation still has stale SP replacement values and RP_SLOTS, and the Beamer slides still say "W" instead of "L."

---

## What the Tool Does (Conceptual Overview)

The tool answers: **"Which available player would most increase my probability of winning a given week?"**

It does this by:

1. Modeling each category as a normal distribution with known mean and SD
2. Computing P(win category) = Phi((my_mean - opp_mean) / (SD * sqrt(2))) for each of 14 categories
3. Summing across categories to get expected weekly wins
4. For each available player: temporarily adding them to your roster, recalculating total expected wins, and reporting the difference (marginal value)
5. Ranking all available players by marginal value, which updates dynamically as you draft

Empty roster slots are filled with **replacement-level production** (derived from players ranked 155-175 in projections), so the tool measures value *above what you'd get from the waiver wire*.

---

## Verified Correct

### Math and Formulas
- **normalCDF**: Abramowitz-Stegun approximation with correct constants (accurate to ~1.5e-7)
- **winProbability**: Formula P(win) = Phi((mu_me - mu_opp) / (SD * sqrt(2))) is correct. The sqrt(2) properly accounts for Var(X-Y) = 2 * sigma^2 when both teams share the same SD
- **getHittingProjections**: Correctly sums counting stats / 25 weeks and averages OBP across 9 hitters
- **getPitchingProjections**: Correctly handles SP (1.1 starts/week per slot) and RP (per-slot weekly rates), computes ERA = ER*9/IP and WHIP = WH/IP
- **getExpectedWins**: Correctly treats SO, L, ERA, WHIP as "lower is better" categories
- **calculateMarginalValue**: Correctly does "add player, measure change, remove player"

### Data Pipeline
- **normalize_pa.py**: Correctly scales counting stats by DC_PA / TheBat_PA while preserving rate stats (OBP, K%). Verified for multiple players
- **create_league_stats.py**: Z-scores computed correctly. PA supplementation formula is correct (blended OBP = weighted average). TARGET_PA raised to 625, applied correctly
- **create_pitching_stats.py**: SP per-start scaling and RP per-week division verified
- **CSV-to-HTML consistency**: All three projection system CSVs (DC, TheBat, BatX) match their corresponding embedded JS arrays in draft_tool.html

### Replacement Level (Updated to 625 PA)
- HITTER_REP at 625 PA matches per-PA rates from create_league_stats.py:
  - R: 625 * 0.121162 = 75.7 -> 76 (correct)
  - HR: 625 * 0.033035 = 20.6 -> 21 (correct)
  - RBI: 625 * 0.120773 = 75.5 -> 75 (correct, rounds down)
  - SO: 625 * 0.222623 = 139.1 -> 140 (minor: rounds to 139 by strict rounding, tool uses 140; difference is negligible)
  - TB: 625 * 0.372522 = 232.8 -> 233 (correct)
  - SB: 625 * 0.015157 = 9.5 -> 9 (correct, rounds down)
  - OBP: 0.324 (matches cohort average)

### Updated Constants (New Since Last Audit)
- **SDs and averages** now use weighted 34% 2024 / 66% 2025 (filtered, excl. weeks 1 & 15). This is correctly implemented in draft_tool.html
- **AVG_OBP = 0.327** is consistent between create_league_stats.py and HITTING_AVG.OBP in draft_tool.html
- **REP_OBP = 0.324** (actual cohort average) is now used instead of the old hardcoded 0.320 cap. This is correct -- replacement players are slightly below league average in OBP, which makes sense
- **PA normalization is single-source**: create_league_stats.py handles all PA supplementation at data generation time; draft_tool.html does not re-normalize. This is clean and correct

---

## Previously-Reported Issues: Status

### ISSUE 1 (Medium, STILL OPEN): `draft_tool.py` is inconsistent with `draft_tool.html`

The Python CLI tool still uses old constants:
- Old 2024-only SDs and averages (not the weighted 2024/2025 values)
- Old replacement level: 1.263x scale factor on ranks 145-160 cohort, producing PA=638, OBP=0.312
- The HTML tool now uses ranks 155-175 cohort, PA=625, OBP=0.324

The gap has actually widened since the HTML tool was updated. **Use the HTML tool for drafting.**

### ISSUE 2 (Low, FIXED): `AI_HANDOFF.md` merge conflict

The merge conflict markers have been resolved. The file is clean.

### ISSUE 3 (Low, FIXED): `AI_HANDOFF.md` had stale SP replacement and RP_SLOTS values

Fixed: SP_REP_PER_START values, RP_SLOTS (3 -> 4), and "multiply by 600 PA" -> 625 now all match the code.

### ISSUE 4 (Low, FIXED): Beamer slides said "W" instead of "L"

Fixed: `draft_tool_docs.tex` now correctly says "L, SV, K, HLD, ERA, WHIP, QS".

### ISSUE 5 (Low, STILL OPEN): `fantasy_hitters_2026.csv` uses non-normalized PA

Same as before -- this default output file isn't used by the HTML tool.

---

## New Observations

### NOTE 1: Keepers are currently cleared

The keepers array in draft_tool.html is set to `[]` (empty) with a comment saying "temporarily cleared to examine player pool with replacement team." The original keepers (Ramirez, Seager, Buxton, Rooker, deGrom, Misiorowski) are preserved in comments. **Remember to restore your keepers before draft day.**

### NOTE 2: Z-score SDs in create_league_stats.py use 2024-only values

The SDs in create_league_stats.py (used for z-score computation) are still the old 2024-only values (SD_R=6.03, SD_OBP=0.04, etc.), while draft_tool.html uses the updated weighted 2024/2025 values (R=6.02, OBP=0.0351, etc.). This is **not a bug** -- the z-scores in the CSV are only used for ranking players to identify the replacement-level cohort (ranks 155-175). The actual draft valuations use the HTML tool's SDs for win probability. However, if you ever regenerate the CSVs, you may want to update these SDs for consistency. The comment in the Python file still says "Weekly standard deviations from 2024 league data" which is accurate but could be confusing alongside the updated AVG_OBP (which IS the weighted value).

---

## Conceptual Observations (Not Bugs)

These are design choices worth understanding, not errors:

1. **The opponent is always "league average"**: The tool doesn't model your specific weekly matchup. This is a reasonable simplification for draft-time rankings.

2. **Both teams assumed to have equal SD**: In reality, teams with more volatile rosters have higher variance. The tool uses the same historical SD for both sides.

3. **No position scarcity modeling**: A catcher-eligible player isn't valued higher just because catchers are scarce. The tool treats all 9 hitter slots equivalently.

4. **Holds are above replacement for a full RP staff**: A full replacement RP staff (4 slots) projects to 3.39 HLD/week vs league average 2.26 (68% win probability). This means RPs who get holds won't improve your HLD category much -- you're already above average from replacement alone. Closers get their value from the saves deficit (0.48 replacement vs 2.17 average = only 19% win probability).

5. **Z-scores in CSVs aren't traditional z-scores**: They're (weekly_stat / SD), not (weekly_stat - mean) / SD. They're valid for ranking but don't represent "standard deviations above average." This doesn't affect the HTML tool, which uses raw stats for marginal value.
