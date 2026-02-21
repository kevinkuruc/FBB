# Draft Tool Audit Report

## Executive Summary

**The core HTML draft tool (`draft_tool.html`) is mathematically sound and the data pipeline is correct.** The win-probability-based marginal value approach is well-designed for H2H category leagues. The data flows from raw projections through normalization to final player arrays without errors.

There are several issues, but none affect the core HTML tool you'll use on draft day. The issues are concentrated in (a) the Python CLI being out of sync with the HTML tool, and (b) stale documentation.

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
- **Worked example**: Ramirez MV = 0.378 verified independently -- all intermediate values match the handoff doc
- **getHittingProjections**: Correctly sums counting stats / 25 weeks and averages OBP across 9 hitters
- **getPitchingProjections**: Correctly handles SP (1.1 starts/week per slot) and RP (per-slot weekly rates), computes ERA = ER*9/IP and WHIP = WH/IP
- **getExpectedWins**: Correctly treats SO, L, ERA, WHIP as "lower is better" categories
- **calculateMarginalValue**: Correctly does "add player, measure change, remove player"

### Data Pipeline
- **normalize_pa.py**: Correctly scales counting stats by DC_PA / TheBat_PA while preserving rate stats (OBP, K%). Verified for multiple players
- **create_league_stats.py**: Z-scores computed correctly. PA supplementation formula is correct (blended OBP = weighted average). Verified Ohtani, Judge, Witt z-scores match CSV output exactly
- **create_pitching_stats.py**: SP per-start scaling and RP per-week division verified for Skubal, Skenes, Miller, Helsley
- **CSV-to-HTML consistency**: All three projection system CSVs (DC, TheBat, BatX) match their corresponding embedded JS arrays in draft_tool.html. Same PA across all three systems (317 common players), different stat projections

### Replacement Level
- Hitter replacement rates verified: 1247/10292 = 0.121162 (R/PA), etc.
- HITTER_REP at 600 PA matches rates: 600 * 0.121162 = 72.7 -> 73 R
- Full replacement team expects 6.15 / 14 category wins (~44%), which is reasonable for "below average" baseline

---

## Issues Found

### ISSUE 1 (Medium): `draft_tool.py` is inconsistent with `draft_tool.html`

The Python CLI tool uses a **completely different replacement level** than the HTML tool:

| Stat | draft_tool.py | draft_tool.html |
|------|--------------|-----------------|
| PA   | 638          | 600             |
| R    | 77           | 73              |
| HR   | 21           | 20              |
| RBI  | 76           | 72              |
| SO   | 143          | 134             |
| TB   | 235          | 224             |
| SB   | 11           | 9               |
| OBP  | 0.312        | 0.320           |

The Python tool uses a 1.263x scale factor on a ranks-145-160 cohort, while the HTML uses per-PA rates from a ranks-155-175 cohort multiplied by 600 PA. These produce different player rankings.

Additionally, the Python CLI:
- **Only handles hitters** (no pitching marginal value)
- **Loads `fantasy_hitters_2026.csv`** (non-normalized The Bat PA) instead of the normalized projection-specific CSVs the HTML uses

**Impact**: If you use the Python CLI, you'll get different rankings than the HTML tool. **Use the HTML tool for drafting.**

### ISSUE 2 (Low): `AI_HANDOFF.md` has unresolved git merge conflict

The entire file is duplicated between `<<<<<<< Updated upstream` and `>>>>>>> Stashed changes` markers. The content of both sides appears identical, so no information is lost, but the file is messy.

### ISSUE 3 (Low): Documentation has stale constants

The handoff doc lists SP_REP_PER_START values that differ from the actual code:

| Stat | Doc says | Code has |
|------|----------|----------|
| ip   | 5.5      | 5.756    |
| l    | 0.11     | 0.3379   |
| qs   | 0.45     | 0.3797   |
| k    | 5.0      | 5.187    |
| er   | 2.5      | 2.688    |
| wh   | 7.0      | 7.448    |

The code values match `create_pitching_stats.py` and are correct. The doc values appear to be from an earlier draft.

The handoff doc also says RP_SLOTS = 3, but the code correctly uses RP_SLOTS = 4.

### ISSUE 4 (Low): Beamer slides say "W" instead of "L"

`draft_tool_docs.tex` line 38 says "Pitching: W, SV, K, HLD, ERA, WHIP, QS" but the actual league category is L (losses, lower is better). The code is correct; the slide has a typo.

### ISSUE 5 (Low): `fantasy_hitters_2026.csv` uses non-normalized PA

The default output of `create_league_stats.py` (no arguments) generates `fantasy_hitters_2026.csv` from raw The Bat data. This file has The Bat's own PA estimates (e.g., Ohtani PA=671) rather than the DC-normalized PA (679) that the HTML tool uses. This file isn't used by the HTML tool, but it could be confusing if someone references it thinking it matches the HTML data.

---

## Conceptual Observations (Not Bugs)

These are design choices worth understanding, not errors:

1. **The opponent is always "league average"**: The tool doesn't model your specific weekly matchup. This is a reasonable simplification for draft-time rankings.

2. **Both teams assumed to have equal SD**: In reality, teams with more volatile rosters have higher variance. The tool uses the same historical SD for both sides.

3. **No position scarcity modeling**: A catcher-eligible player isn't valued higher just because catchers are scarce. The tool treats all 9 hitter slots equivalently.

4. **Holds are above replacement for a full RP staff**: A full replacement RP staff (4 slots) projects to 3.39 HLD/week vs league average 2.30 (68% win probability). This means RPs who get holds won't improve your HLD category much -- you're already above average from replacement alone. Closers get their value from the saves deficit (0.48 replacement vs 2.27 average = only 21% win probability).

5. **Z-scores in CSVs aren't traditional z-scores**: They're (weekly_stat / SD), not (weekly_stat - mean) / SD. They're valid for ranking but don't represent "standard deviations above average." This doesn't affect the HTML tool, which uses raw stats for marginal value.
