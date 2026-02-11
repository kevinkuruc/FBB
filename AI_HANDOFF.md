# Fantasy Baseball Draft Tool - Technical Documentation

This document is designed for AI handoff. It contains everything needed to understand and modify the codebase.

## Repository Structure

```
/home/user/FBB/
├── draft_tool.html           # Main app (HTML + JS, ~1200 lines)
├── create_league_stats.py    # Generates hitter CSVs with z-scores
├── create_pitching_stats.py  # Generates pitcher CSVs
├── normalize_pa.py           # Aligns PA across projection systems
│
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
3. `create_league_stats.py`: Calculate z-scores, supplement low-PA players to 600 PA
4. Output CSVs are manually embedded as JS arrays in `draft_tool.html`

**WARNING:** Player arrays in draft_tool.html are generated separately. If you regenerate CSVs, you must manually copy the data into the JS arrays.

---

## Key Constants (draft_tool.html)

### Weekly Standard Deviations (Lines 482-483)

From 2024 league weekly results. These determine category leverage.

```javascript
const HITTING_SD = {
    R: 6.03, HR: 2.93, RBI: 6.72, SB: 2.57,
    SO: 7.45, TB: 15.94, OBP: 0.04, AB: 16.89
};

const PITCHING_SD = {
    L: 1.8346, SV: 1.5362, K: 11.7861, HLD: 1.6383,
    ERA: 1.3141, WHIP: 0.2057, QS: 1.4012, IP: 10.82
};
```

### League Averages (Lines 486-487)

Used as opponent baseline in win probability calculations.

```javascript
const HITTING_AVG = {
    R: 28.96, HR: 8.02, RBI: 27.86, SB: 4.74,
    SO: 50.11, TB: 88.87, OBP: 0.32, AB: 208.3
};

const PITCHING_AVG = {
    L: 3.08, SV: 2.27, K: 50.90, HLD: 2.30,
    ERA: 3.79, WHIP: 1.20, QS: 3.25, IP: 51.0
};
```

### Replacement Level (Lines 489-510)

```javascript
// Hitter replacement - 600 PA SEASON TOTALS
const HITTER_REP = {
    name: 'Replacement', type: 'H', pa: 600,
    r: 73, hr: 20, rbi: 72, so: 134,
    tb: 224, sb: 9, obp: 0.32
};

// RP replacement - PER SLOT, WEEKLY
const RP_REP_PER_SLOT = {
    ip_wk: 2.480, l_wk: 0.1180, sv_wk: 0.1208,
    hld_wk: 0.8484, k_wk: 2.693,
    er_wk: 0.963, wh_wk: 2.852
};

// SP replacement - PER START
const SP_REP_PER_START = {
    ip: 5.5, l: 0.11, qs: 0.45,
    k: 5.0, er: 2.5, wh: 7.0
};
```

**Where hitter replacement comes from** (defined in create_league_stats.py):
- Rank all hitters by zTotal using Depth Charts projections
- Take players ranked 155-175 (just beyond 16 teams × 9 hitters = 144)
- Average their per-PA rates, multiply by 600 PA

**WARNING:** Replacement OBP is hardcoded to 0.320 (league average) because the cohort's actual OBP (0.324) exceeded it. Replacement should be neutral, not positive.

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
- RP_SLOTS = 3
- Empty slots filled with replacement production
- ERA = (total_er × 9) / total_ip
- WHIP = total_wh / total_ip

**WARNING:** SP stats in PITCHERS array are already scaled to 1.1 starts/week. Don't double-scale.

### calculateMarginalValue (Lines 724-753)

```javascript
function calculateMarginalValue(player) {
    const team = allTeams['My Team'];
    const currentWins = getExpectedWins('My Team').wins.TOTAL;

    // Temporarily add player to first empty slot
    if (player.type === 'H') {
        const idx = team.hitters.findIndex(s => s.player === null);
        if (idx === -1) return -999;  // No empty slot
        team.hitters[idx].player = player;
        newWins = getExpectedWins('My Team').wins.TOTAL;
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

```python
TARGET_PA = 600

if pa < TARGET_PA:
    gap_pa = TARGET_PA - pa
    runs = runs + gap_pa * REP_R_PER_PA
    hr = hr + gap_pa * REP_HR_PER_PA
    # ... other counting stats ...
    obp = (pa * obp + gap_pa * REP_OBP) / TARGET_PA
    pa = TARGET_PA
```

**Purpose:** A player with 400 PA shouldn't look worse just due to fewer counting stats. We fill the gap with replacement-level production.

### Replacement Level Rates (create_league_stats.py)

```python
# From players ranked 155-175 in DC projections
REP_R_PER_PA = 0.121162    # 1247 R / 10292 PA
REP_HR_PER_PA = 0.033035   # 340 HR / 10292 PA
REP_RBI_PER_PA = 0.120773  # 1243 RBI / 10292 PA
REP_SO_PER_PA = 0.222623   # 2291 SO / 10292 PA
REP_TB_PER_PA = 0.372522   # 3834 TB / 10292 PA
REP_SB_PER_PA = 0.015157   # 156 SB / 10292 PA
REP_OBP = 0.320            # Hardcoded at league average
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
    {"name":"Shohei Ohtani","type":"H","pa":679,"r":126,"hr":48,"rbi":119,"so":160,"tb":347,"sb":24,"obp":0.385},
    // ...
];

const HITTERS_DC = [...];
const HITTERS_BATX = [...];

const PITCHERS = [
    {"name":"Tarik Skubal","type":"SP","gs":29.6,"ip_wk":7.03,"l_wk":0.259,"sv_wk":0.0,"hld_wk":0.0,"k_wk":8.48,"qs_wk":0.673,"er_wk":2.17,"wh_wk":6.854,...},
    // ...
];
```

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

`allTeams['My Team'].hitters` = 9 slots, all null.

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

## Common Gotchas

1. **Hitter stats are season totals; pitcher stats are weekly** - Don't mix them up when doing calculations.

2. **Empty slots auto-fill with replacement** - This is how "vs replacement" works. An empty roster has 9 replacement hitters.

3. **OBP divides by 9** in z-score calculation - One player contributes 1/9 of team OBP.

4. **Replacement OBP is hardcoded** to 0.320 - Not computed from the cohort.

5. **SP ip_wk is already scaled** to 1.1 starts/week in PITCHERS array - Don't multiply again.

6. **ERA/WHIP are ratio stats** - RPs contribute ~6% of team innings, so their ERA/WHIP impact is tiny.

7. **Player arrays are embedded in HTML** - Regenerating CSVs requires manual copy of data into JS arrays.

8. **Marginal value depends on current roster** - As you draft players, MV changes for remaining players.

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
8. OBP cap at league average (0.320)
9. The BatX projection system added

**Add new features here with: what changed, which files, any gotchas.**

---

## Quick Reference: Key Lines in draft_tool.html

| What | Lines |
|------|-------|
| HITTERS arrays | 438-480 |
| PITCHERS array | 480 |
| HITTING_SD, PITCHING_SD | 482-483 |
| HITTING_AVG, PITCHING_AVG | 486-487 |
| HITTER_REP, RP_REP, SP_REP | 489-510 |
| normalCDF | 580-592 |
| winProbability | 594-599 |
| getHittingProjections | 604-615 |
| getPitchingProjections | 617-690 |
| getExpectedWins | 692-720 |
| calculateMarginalValue | 724-753 |
| renderAvailablePlayers | 877-980 |

**WARNING:** Line numbers drift as code is edited. Use function names to search.
