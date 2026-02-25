# Fantasy Baseball Draft Tool - Technical Documentation

This document is designed for AI handoff. It contains everything needed to understand and modify the codebase.

## Repository Structure

```
/home/user/FBB/
├── draft_tool.html           # Main app (HTML + JS, ~1300 lines)
├── add_fantrax_data.py       # Patches HTML with Fantrax data (keepers, positions)
├── create_league_stats.py    # Generates hitter CSVs with z-scores
├── create_pitching_stats.py  # Generates pitcher CSVs
├── normalize_pa.py           # Aligns PA across projection systems
│
├── Fantrax-Players-Kevin's League.csv  # Fantrax roster export (positions, team ownership)
├── DC_Raw_Jan_25.csv         # Depth Charts raw projections (source of truth for PA)
├── The_Bat_Raw_Jan_25.csv    # The Bat raw projections
├── The_BatX_Raw_Jan_25.csv   # The BatX raw projections
│
├── The_Bat_Normalized_PA.csv  # The Bat with PA scaled to match DC
├── The_BatX_Normalized_PA.csv # BatX with PA scaled to match DC
│
├── fantasy_hitters_dc_2026.csv     # Processed hitters (DC projections)
├── fantasy_hitters_thebat_2026.csv # Processed hitters (The Bat)
├── fantasy_hitters_batx_2026.csv   # Processed hitters (BatX)
│
├── AI_HANDOFF.md             # This file (technical docs for AI)
└── draft_tool_docs.pdf       # Beamer slides (methodology for humans)
```

## Data Flow

1. Raw projections downloaded from FanGraphs (DC, The Bat, BatX)
2. `normalize_pa.py`: Scale The Bat/BatX counting stats to use DC playing time
3. `create_league_stats.py`: Calculate z-scores, supplement low-PA players to 625 PA
4. Output CSVs are manually embedded as JS arrays in `draft_tool.html`
5. `add_fantrax_data.py`: Patches the HTML with Fantrax data (positional eligibility, keepers, team names)

**WARNING:** Player arrays in draft_tool.html are generated separately. If you regenerate CSVs, you must manually copy the data into the JS arrays, then re-run `add_fantrax_data.py` to re-apply Fantrax data.

---

## Key Constants (draft_tool.html)

### Weekly Standard Deviations (Lines 482-483)

Weighted average: 34% 2024, 66% 2025 (filtered, excl. weeks 1 & 15). These determine category leverage.

```javascript
const HITTING_SD = {
    R: 6.02, HR: 3.04, RBI: 6.89, SB: 2.57,
    SO: 7.96, TB: 15.98, OBP: 0.0351, AB: 20.27
};

const PITCHING_SD = {
    L: 1.8012, SV: 1.5509, K: 13.4752, HLD: 1.5596,
    ERA: 1.3062, WHIP: 0.2108, QS: 1.4334, IP: 10.82
};
```

### League Averages (Lines 486-487)

Weighted average: 34% 2024, 66% 2025 (filtered). Used as opponent baseline.

```javascript
const HITTING_AVG = {
    R: 29.43, HR: 8.41, RBI: 28.65, SB: 4.78,
    SO: 49.93, TB: 90.72, OBP: 0.327, AB: 209.8
};

const PITCHING_AVG = {
    L: 3.15, SV: 2.17, K: 51.30, HLD: 2.26,
    ERA: 3.80, WHIP: 1.22, QS: 3.21, IP: 51.0
};
```

### Replacement Level (Lines 489-510)

```javascript
// Hitter replacement - 625 PA SEASON TOTALS (matches TARGET_PA in create_league_stats.py)
const HITTER_REP = {
    name: 'Replacement', type: 'H', pa: 625,
    r: 76, hr: 21, rbi: 75, so: 140,
    tb: 233, sb: 9, obp: 0.324
};

// RP replacement - PER SLOT, WEEKLY
const RP_REP_PER_SLOT = {
    ip_wk: 2.480, l_wk: 0.1180, sv_wk: 0.1208,
    hld_wk: 0.8484, k_wk: 2.693,
    er_wk: 0.963, wh_wk: 2.852
};

// SP replacement - PER START
const SP_REP_PER_START = {
    ip: 5.756, l: 0.3379, qs: 0.3797,
    k: 5.187, er: 2.688, wh: 7.448
};
```

**Where hitter replacement comes from** (defined in create_league_stats.py):
- Rank all hitters by zTotal using Depth Charts projections
- Take players ranked 155-175 (just beyond 16 teams × 9 hitters = 144)
- Average their per-PA rates, multiply by 625 PA

**NOTE:** Replacement OBP (0.324) is the actual cohort average. League average OBP (0.327) is slightly higher, so replacement players are slightly below average in OBP.

---

## Core Functions (draft_tool.html)

### normalCDF (Lines 580-592)

Abramowitz-Stegun approximation of standard normal CDF.

```javascript
function normalCDF(x) {
    const a1 =  0.254829592;
    const a2 = -0.284496736;
    const a3 =  1.421413741;
    const a4 = -1.453152027;
    const a5 =  1.061405429;
    const p  =  0.3275911;
    const sign = x < 0 ? -1 : 1;
    x = Math.abs(x) / Math.sqrt(2);
    const t = 1.0 / (1.0 + p * x);
    const y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
    return 0.5 * (1.0 + sign * y);
}
```

### winProbability (Lines 594-599)

```javascript
function winProbability(myMean, oppMean, sd, lowerIsBetter = false) {
    const z = lowerIsBetter
        ? (oppMean - myMean) / (sd * Math.sqrt(2))
        : (myMean - oppMean) / (sd * Math.sqrt(2));
    return normalCDF(z);
}
```

**Formula:** P(win) = Φ((μ_me - μ_opp) / (σ × √2))

The √2 comes from Var(X-Y) = Var(X) + Var(Y) = 2σ² when both teams have same variance.

### getHittingProjections (Lines 604-615)

```javascript
function getHittingProjections(teamName) {
    const roster = allTeams[teamName].hitters;
    // Empty slots use HITTER_REP
    const players = roster.map(slot => slot.player || HITTER_REP);

    const proj = {};
    ['r', 'hr', 'rbi', 'sb', 'so', 'tb'].forEach(cat => {
        proj[cat.toUpperCase()] = players.reduce((sum, p) => sum + p[cat] / NUM_WEEKS, 0);
    });
    // OBP is average across 9 hitters
    proj['OBP'] = players.reduce((sum, p) => sum + p.obp, 0) / players.length;
    return proj;
}
```

**WARNING:** Empty slots auto-fill with HITTER_REP. This is how "vs replacement" works.

### getPitchingProjections (Lines 617-690)

Key points:
- SP_SLOTS = 7, each gets 1.1 starts/week
- RP_SLOTS = 4
- Empty slots filled with replacement production
- ERA = (total_er × 9) / total_ip
- WHIP = total_wh / total_ip

**WARNING:** SP stats in PITCHERS array are already scaled to 1.1 starts/week. Don't double-scale.

### calculateMarginalValue

```javascript
function calculateMarginalValue(player) {
    const team = allTeams['Skrey'];
    const currentWins = getExpectedWins('Skrey').wins.TOTAL;

    // Temporarily add player to first empty slot
    if (player.type === 'H') {
        const idx = team.hitters.findIndex(s => s.player === null);
        if (idx === -1) return -999;  // No empty slot
        team.hitters[idx].player = player;
        newWins = getExpectedWins('Skrey').wins.TOTAL;
        team.hitters[idx].player = null;  // Restore
    }
    // Similar for SP, RP...

    return newWins - currentWins;
}
```

This is **the core ranking function**. It answers: "How many expected category wins does this player add vs. having a replacement player in that slot?"

---

## CSV Generation (create_league_stats.py)

### Z-Score Formulas

For counting stats (R, HR, RBI, TB, SB):
```python
z_r = (runs / NUM_WEEKS) / SD_R
```

For strikeouts (lower is better):
```python
z_so = -(strikeouts / NUM_WEEKS) / SD_SO
```

For OBP (rate stat):
```python
z_obp = (obp - AVG_OBP) / 9 / SD_OBP
```

**NOTE:** The /9 on OBP accounts for one player contributing 1/9 of team OBP. Without it, OBP would be overweighted.

### PA Supplementation

**SINGLE SOURCE OF TRUTH: create_league_stats.py**

PA normalization happens ONLY in create_league_stats.py at data generation time.
Do NOT add PA normalization in draft_tool.html - data arrives pre-normalized.

```python
# create_league_stats.py
TARGET_PA = 625  # All players supplemented to this level

if pa < TARGET_PA:
    gap_pa = TARGET_PA - pa
    runs = runs + gap_pa * REP_R_PER_PA
    hr = hr + gap_pa * REP_HR_PER_PA
    rbi = rbi + gap_pa * REP_RBI_PER_PA
    so = so + gap_pa * REP_SO_PER_PA
    tb = tb + gap_pa * REP_TB_PER_PA
    sb = sb + gap_pa * REP_SB_PER_PA
    obp = (pa * obp + gap_pa * REP_OBP) / TARGET_PA
    pa = TARGET_PA
```

**Example:** Corey Seager with raw 560 PA → 625 PA in data (65 replacement PAs added)

**Purpose:** All hitters evaluated on equal playing time basis. Low-PA players get replacement-level production for missing PAs.

**To change the PA floor:**
1. Update `TARGET_PA` in create_league_stats.py
2. Regenerate all three CSVs (DC, The Bat, BatX)
3. Update JS arrays in draft_tool.html (use conversion script)
4. Update `HITTER_REP` in draft_tool.html to match new PA level

### Replacement Level Rates (create_league_stats.py)

```python
# From players ranked 155-175 in DC projections
REP_R_PER_PA = 0.121162    # 1247 R / 10292 PA
REP_HR_PER_PA = 0.033035   # 340 HR / 10292 PA
REP_RBI_PER_PA = 0.120773  # 1243 RBI / 10292 PA
REP_SO_PER_PA = 0.222623   # 2291 SO / 10292 PA
REP_TB_PER_PA = 0.372522   # 3834 TB / 10292 PA
REP_SB_PER_PA = 0.015157   # 156 SB / 10292 PA
REP_OBP = 0.324            # Actual cohort average (ranks 155-175)
```

---

## PA Normalization (normalize_pa.py)

```python
# Scale The Bat stats to match DC playing time
scale = dc_pa[name] / thebat_pa

counting_stats = ['AB', 'H', '1B', '2B', '3B', 'HR', 'R', 'RBI', 'BB', 'SO', 'SB', 'CS', ...]

for stat in counting_stats:
    new_row[stat] = original * scale

# Rate stats (OBP, K%) unchanged
```

**Purpose:** Compare projection skill, not playing time estimates. All systems use DC's PA.

---

## Player Data Arrays (draft_tool.html, Lines 438-480)

```javascript
const HITTERS_THEBAT = [
    {"name":"Shohei Ohtani","type":"H","pa":679,"r":126,"hr":48,"rbi":119,"so":160,"tb":347,"sb":24,"obp":0.385,"pos":["UT"]},
    // ...
];

const HITTERS_DC = [...];  // Same shape, different projections
const HITTERS_BATX = [...];

const PITCHERS = [
    {"name":"Tarik Skubal","type":"SP","gs":29.6,"ip_wk":7.03,"l_wk":0.259,"sv_wk":0.0,"hld_wk":0.0,"k_wk":8.48,"qs_wk":0.673,"er_wk":2.17,"wh_wk":6.854,...},
    {"name":"Some Reliever","type":"RP",...,"dualEligible":true},  // SP/RP eligible
    // ...
];
```

**Fields added by add_fantrax_data.py:**
- Hitters: `pos` (array of eligible positions, e.g. `["LF","CF","RF","UT"]`) — used by position optimizer and UI badges
- Pitchers: `dualEligible` (boolean, true if eligible at both SP and RP) — displayed as badge in UI

**WARNING:** Hitter stats are SEASON TOTALS. Pitcher stats are ALREADY WEEKLY.

### Projection Toggle

```javascript
let currentProjection = 'thebat';  // default

function getHitters() {
    if (currentProjection === 'thebat') return HITTERS_THEBAT;
    if (currentProjection === 'batx') return HITTERS_BATX;
    return HITTERS_DC;
}
```

**NOTE:** PITCHERS array is shared across all projection systems (not toggled).

---

## Worked Example: Ramírez Marginal Value

### Setup: Empty Roster

`allTeams['Skrey'].hitters` = 9 slots, all null (after keepers are loaded, some slots are filled).

`getHittingProjections` fills nulls with `HITTER_REP`:

| Stat | Team Weekly Total |
|------|-------------------|
| R | 9 × 73/25 = 26.28 |
| HR | 9 × 20/25 = 7.20 |
| RBI | 9 × 72/25 = 25.92 |
| SO | 9 × 134/25 = 48.24 |
| TB | 9 × 224/25 = 80.64 |
| SB | 9 × 9/25 = 3.24 |
| OBP | 0.320 |

### Win Probabilities: Replacement Team

| Cat | My Team | Opp (AVG) | SD | P(win) |
|-----|---------|-----------|-----|--------|
| R | 26.28 | 28.96 | 6.03 | 37.7% |
| HR | 7.20 | 8.02 | 2.93 | 42.2% |
| RBI | 25.92 | 27.86 | 6.72 | 41.9% |
| SO | 48.24 | 50.11 | 7.45 | 57.0% |
| TB | 80.64 | 88.87 | 15.94 | 35.8% |
| SB | 3.24 | 4.74 | 2.57 | 34.0% |
| OBP | 0.320 | 0.320 | 0.04 | 50.0% |

**currentWins** = Σ P = 2.99

### Add Ramírez

Ramírez: 679 PA, 98 R, 30 HR, 94 RBI, 78 SO, 300 TB, 34 SB, .348 OBP

Team becomes 8 replacement + Ramírez:

| Cat | Before | After | Δ |
|-----|--------|-------|---|
| R | 26.28 | 27.28 | +1.00 |
| HR | 7.20 | 7.60 | +0.40 |
| RBI | 25.92 | 26.80 | +0.88 |
| SO | 48.24 | 46.00 | -2.24 |
| TB | 80.64 | 83.68 | +3.04 |
| SB | 3.24 | 4.24 | +1.00 |
| OBP | 0.320 | 0.323 | +0.003 |

**NOTE:** OBP shifts by (0.348-0.320)/9 = 0.003 because it's averaged across 9 hitters.

### New Win Probabilities

| Cat | Old P | New P | ΔP |
|-----|-------|-------|-----|
| R | 37.7% | 42.2% | +4.5% |
| HR | 42.2% | 46.0% | +3.8% |
| RBI | 41.9% | 45.6% | +3.6% |
| SO | 57.0% | 65.2% | +8.1% |
| TB | 35.8% | 40.9% | +5.1% |
| SB | 34.0% | 44.5% | +10.5% |
| OBP | 50.0% | 52.2% | +2.2% |
| **Total** | 2.99 | 3.36 | **+0.378** |

**marginalValue = 3.36 - 2.99 = 0.378**

This is what the UI shows as "+MV" for Ramírez.

---

## Fantrax Integration (add_fantrax_data.py)

### Overview

`add_fantrax_data.py` reads the Fantrax CSV export and patches `draft_tool.html` with:
1. **Positional eligibility** (`pos` field) on all hitter arrays — e.g. `"pos":["LF","CF","RF","UT"]`
2. **Dual SP/RP eligibility** (`dualEligible` field) on pitchers who qualify for both
3. **Keepers** — a `KEEPERS` JSON object embedded in `initKeepers()`, keyed by Fantrax team name
4. **Team names** — `TEAM_NAMES` array updated to use Fantrax team names instead of placeholders

### Name Matching

Projection names (with accents like "José Ramírez") must match Fantrax names (often without accents, "Jose Ramirez"). The script uses aggressive normalization:

```python
def normalize(name):
    # Strip accents (NFKD decomposition), lowercase, remove apostrophes/hyphens/periods
    # "José Ramírez" -> "jose ramirez"
    # "Tyler O'Neill" -> "tyler oneill"
    # "C.J. Kayfus" -> "cj kayfus"
```

**Duplicate name handling:** Fantrax has ~10,000 players including minors, so names like "Jose Ramirez" appear multiple times (3B star, minor league RP, minor league RF). The script keeps the highest-ranked entry (lowest `RkOv` value) for each normalized name.

**Special case:** Shohei Ohtani appears as "Shohei Ohtani-H" (hitter) and "Shohei Ohtani-P" (pitcher) in Fantrax but just "Shohei Ohtani" in hitter projections. The script maps "Shohei Ohtani" → the "-H" entry.

### Re-running After Data Changes

If you update projection CSVs or the Fantrax CSV:
1. Update the JS player arrays in `draft_tool.html` (from new CSVs)
2. Run `python3 add_fantrax_data.py` — this patches the HTML in-place
3. The script is idempotent but expects the HTML to have the original (un-patched) player arrays, so reset the HTML with `git checkout -- draft_tool.html` before re-running if it was already patched

### Team Name Mapping

The 16-team league uses Fantrax display names. The user's team is "Skrey". All references to team names in the JS code use these Fantrax names.

```
Skrey, JDM, BigJoe, Ferrante, Rut, Gwon, Beefs, Unks,
Swagga, Triz, Boofers, BShit, DertyDer, wes11, DGreasy, Diarrhea
```

---

## Keepers and Position Optimizer (draft_tool.html)

### Keeper Initialization

At startup, `initKeepers()` loads all keepers onto their teams from the embedded `KEEPERS` object. Hitters are placed into any empty slot, then `optimizeTeamPositions()` is called to sort them into optimal positions.

Keepers that don't match any player in the projection arrays (e.g. prospects like Konnor Griffin) are silently skipped.

### Position Optimizer

`optimizeTeamPositions(teamName)` re-assigns all hitters on a team to optimal position slots using most-constrained-first greedy matching:

1. Collects all rostered hitters and clears all slots
2. For each player, determines eligible slots from their `pos` array (plus UTIL for everyone)
3. Sorts players by number of eligible slots (fewest first)
4. Assigns each player to their first available non-UTIL slot, falling back to UTIL

**When it runs:**
- After loading keepers for each team in `initKeepers()`
- After every hitter draft pick in `confirmDraft()`

**Example:** Boofers has Yordan Alvarez (LF) and James Wood (LF). The optimizer assigns Yordan to LF (processed first, fewer options) and Wood to UTIL. If a CF is later drafted, the optimizer re-runs and might move Wood to a different slot if it frees up better assignments.

**Not used for "My Roster" (Skrey)** — the user explicitly picks their own slots when drafting.

---

## UI: All Teams Tab and Team Detail View

### All Teams Tab

Displays a 4-column grid of lineup cards. Each card shows:
- Team name + expected weekly wins (e.g. "BigJoe  7.2 W")
- Full hitter lineup: C, 1B, 2B, SS, 3B, LF, CF, RF, UTIL
- All 7 SP slots and 4 RP slots
- Empty slots shown as "—"

### Team Detail View

**Double-clicking** any team card opens a full detail view (same layout as "My Roster") showing:
- All roster slots with per-player stats (R, HR, RBI, SB, OBP for hitters; K, ERA for SP; SV, HLD for RP)
- Position eligibility badges on hitters
- Category win probability tables (hitting + pitching) with color coding
- Expected weekly wins total out of 14
- "Back to All Teams" button returns to grid view

The detail view is rendered by `showTeamDetail(teamName)` into `#team-detail-panel`. It's a separate hidden panel (not a tab) that takes over the display when activated.

### Player Position Badges

Hitters display their Fantrax positional eligibility as small green badges (e.g. `C` `1B` `LF`) next to their name in:
- Best Available list (available-panel)
- My Roster view (roster-panel)
- Team Detail view (team-detail-panel)

Pitchers with dual SP/RP eligibility show an `SP/RP` badge.

### Position Filter Dropdown

The Best Available tab has a `<select>` dropdown (`#pos-filter`) next to the search box that filters the player list by positional eligibility. Options: All Positions, C, 1B, 2B, SS, 3B, LF, CF, RF, SP, RP.

**Filter logic** (in `renderAvailablePlayers`, third parameter `posFilter`):
- **Hitter positions** (C, 1B, 2B, SS, 3B, LF, CF, RF): Shows only hitters whose `pos` array includes that position.
- **SP**: Shows all SP-typed pitchers plus RP-typed pitchers with `dualEligible: true`.
- **RP**: Shows all RP-typed pitchers plus SP-typed pitchers with `dualEligible: true`.
- **All Positions** (empty string): No position filtering applied.

The search box and position filter work together — both are passed to `renderAvailablePlayers` on every change event. The position filter is reset to "All Positions" when `selectSlotForDraft()` switches to the Best Available tab.

---

## Common Gotchas

1. **Hitter stats are season totals; pitcher stats are weekly** - Don't mix them up when doing calculations.

2. **Empty slots auto-fill with replacement** - This is how "vs replacement" works. An empty roster has 9 replacement hitters.

3. **OBP divides by 9** in z-score calculation - One player contributes 1/9 of team OBP.

4. **Replacement OBP is 0.324** - Actual cohort average, slightly below league avg (0.327).

5. **SP ip_wk is already scaled** to 1.1 starts/week in PITCHERS array - Don't multiply again.

6. **ERA/WHIP are ratio stats** - RPs contribute ~6% of team innings, so their ERA/WHIP impact is tiny.

7. **Player arrays are embedded in HTML** - Regenerating CSVs requires manual copy of data into JS arrays.

8. **Marginal value depends on current roster** - As you draft players, MV changes for remaining players.

9. **add_fantrax_data.py expects un-patched HTML** - It replaces player arrays and the `initKeepers()` block. If the HTML was already patched, `git checkout -- draft_tool.html` first, then re-run.

10. **Fantrax name collisions** - ~157 duplicate normalized names in the 10k-player Fantrax CSV. The script keeps the highest-ranked (lowest RkOv) entry. If a new projection player shares a name with a minor leaguer, verify the match is correct.

11. **Keepers missing from projections are silently skipped** - If a keeper (e.g. a prospect) doesn't appear in any projection array, `initKeepers()` just skips them. No error, no slot filled.

12. **Team name is 'Skrey', not 'My Team'** - All JS references use the Fantrax team name. `calculateMarginalValue` is hardcoded to evaluate against Skrey's roster.

13. **Position optimizer doesn't run for Skrey's own roster** - The user explicitly picks slots via the My Roster tab. Only other teams get auto-optimized.

---

## SD Interpretation

Two related but different metrics:

**1/SD = marginal leverage per unit** (used for player valuation)
- SB: 1/2.57 = 0.39 (high leverage)
- K: 1/11.79 = 0.08 (low leverage)

**CV = SD/Mean = category noise** (how luck-dependent)
- SB: 2.57/4.74 = 54% (very noisy)
- SO: 7.45/50.11 = 15% (stable)

For marginal value calculations, only absolute SD matters. CV tells you how luck-dependent a category is, but doesn't change the valuation formula.

---

## Feature History (Chronological)

1. Base draft tool with UI and player data
2. Marginal win probability calculation
3. PA supplementation to 600 PA floor
4. Projection toggle (The Bat vs Depth Charts)
5. PA normalization across projection systems
6. 300 PA minimum filter
7. Replacement recalibration (ranks 155-175 cohort)
8. The BatX projection system added
9. Weighted SD/AVG using 34% 2024 + 66% 2025 filtered data
10. Replacement OBP updated to actual cohort value (0.324)
11. Fantrax integration: positional eligibility, keepers, team names (`add_fantrax_data.py` + `draft_tool.html`)
12. Position optimizer: auto-assigns hitters to optimal slots using most-constrained-first matching
13. All Teams tab: full lineup cards with expected weekly wins, replacing compact mini-roster
14. Team Detail view: double-click any team for full roster/projections/win probabilities
15. Position filter dropdown on Best Available tab: filters players by positional eligibility (C, 1B, 2B, SS, 3B, LF, CF, RF, SP, RP). Hitters are filtered by their `pos` array; SP/RP filters include dual-eligible pitchers. (`draft_tool.html`)

**Add new features here with: what changed, which files, any gotchas.**

---

## League Data Files

Historical weekly matchup data used to calculate SDs and league averages.

### Files

| File | Format | Observations |
|------|--------|--------------|
| `2024_weeklyresults.xlsx` | Wide (Team, Week, Categories...) | 288 (18 weeks × 16 teams) |
| `matchup_stats_2025.csv` | Long (Week, Category, Teams...) | 384 rows |
| `weekly_results_2025.csv` | Wide (converted from above) | 364 (24 weeks × 16 teams) |

### Format Conversion (2025 Long → Wide)

The 2025 data came in "long" format with one row per category per week. To convert:

```python
import pandas as pd

df_raw = pd.read_csv('matchup_stats_2025.csv')
df_melted = df_raw.melt(id_vars=['Week', 'Category'], var_name='Team', value_name='Value')
df_wide = df_melted.pivot_table(index=['Week', 'Team'], columns='Category', values='Value', aggfunc='first').reset_index()
df_wide = df_wide.rename(columns={'K_B': 'K', 'K_P': 'K.1'})  # Match 2024 column names
```

### 2024 vs 2025 Standard Deviation Comparison

**IMPORTANT:** 2025 data excludes Week 1 (Opening Week) and Week 15 (All-Star Break double week). These were longer weeks with ~340 and ~309 avg AB respectively, vs ~210 for normal weeks. Including them inflated all counting stat variances by 30-130%.

With those weeks removed, 2024 and 2025 SDs are very similar:

| Category | 2024 SD | 2025 SD (filtered) | Change |
|----------|---------|-------------------|--------|
| R | 6.03 | 6.02 | -0.2% |
| SB | 2.57 | 2.57 | -0.3% |
| TB | 15.94 | 16.00 | +0.3% |
| RBI | 6.72 | 6.99 | +4.0% |
| HR | 2.93 | 3.09 | +5.6% |
| K (batting) | 7.45 | 8.22 | +10.3% |
| K (pitching) | 11.79 | 14.27 | +21.1% |
| SV | 1.54 | 1.56 | +1.4% |
| HLD | 1.64 | 1.52 | -7.4% |
| ERA | 1.31 | 1.30 | -0.8% |
| WHIP | 0.21 | 0.21 | +3.4% |

### Weighted Average Methodology

The tool uses a **34/66 weighted average** (34% 2024, 66% 2025 filtered) to favor recent data while smoothing noise.

For SDs, use variance weighting: `SD_combined = √(0.34×SD₂₀₂₄² + 0.66×SD₂₀₂₅²)`

For means: `Mean_combined = 0.34×Mean₂₀₂₄ + 0.66×Mean₂₀₂₅`

---

## Quick Reference: Key Functions in draft_tool.html

Use function names to search — line numbers drift as code is edited.

| Function / Block | Purpose |
|------------------|---------|
| `HITTERS_THEBAT`, `HITTERS_BATX`, `HITTERS_DC` | Hitter data arrays (season totals, with `pos` field from Fantrax) |
| `PITCHERS` | Pitcher data array (weekly stats, with `dualEligible` flag) |
| `HITTING_SD`, `PITCHING_SD` | Weekly standard deviations per category |
| `HITTING_AVG`, `PITCHING_AVG` | League average weekly production per category |
| `HITTER_REP`, `RP_REP_PER_SLOT`, `SP_REP_PER_START` | Replacement-level baselines |
| `optimizeTeamPositions(teamName)` | Re-assigns hitters to optimal position slots |
| `initKeepers()` | IIFE that loads keepers from embedded KEEPERS object |
| `normalCDF(x)` | Abramowitz-Stegun normal CDF approximation |
| `winProbability(myMean, oppMean, sd, lowerIsBetter)` | P(win) for a category matchup |
| `getHittingProjections(teamName)` | Weekly hitting projections (empty slots → replacement) |
| `getPitchingProjections(teamName)` | Weekly pitching projections (empty slots → replacement) |
| `getExpectedWins(teamName)` | Total expected wins across all 14 categories |
| `calculateMarginalValue(player)` | Marginal wins added to Skrey's roster |
| `renderRoster()` | Renders My Roster tab (Skrey only) |
| `renderAvailablePlayers(filter, typeFilter, posFilter)` | Best Available list with +MV ranking (posFilter filters by position eligibility) |
| `renderOtherTeams()` | All Teams grid with lineup cards |
| `showTeamDetail(teamName)` | Full detail view for any team (double-click) |
| `backToAllTeams()` | Returns from detail view to All Teams grid |
| `confirmDraft()` | Drafts player to selected team + slot, runs optimizer |
| `draftToSlot(player)` | Quick-draft to Skrey's pending slot (click-to-draft flow) |
