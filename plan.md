# Plan: Add Keepers & Positional Eligibility from Fantrax Data

## Context

The Fantrax CSV (`Fantrax-Players-Kevin's League.csv`) has ~10K players with:
- **Position**: Fantrax positional eligibility (e.g. `"LF,CF,RF,UT"`, `"SP"`, `"C,1B"`)
- **Status**: Either `"FA"` (free agent) or a team name (e.g. `"Skrey"`, `"Boofers"`) indicating they're a keeper

There are **16 teams** with **93 total keepers** (4-8 per team). The Fantrax team names differ from the current HTML team names (e.g. `"Skrey"` vs `"My Team"`, `"Boofers"` vs `"Bish"`, etc.).

## Changes

### 1. Update TEAM_NAMES and add a Fantrax-to-HTML name mapping

The current HTML has placeholder names: `['My Team', 'JDM', 'Calabria', ...]`. We need to either:
- **Replace them** with the actual Fantrax team names (`Skrey`, `Boofers`, `DGreasy`, etc.)
- Or add a mapping between the two

**Recommendation**: Replace `TEAM_NAMES` with the actual Fantrax names. The current names appear to be stale placeholders anyway. This keeps things simple — one name per team, matching the Fantrax source of truth.

The Fantrax teams are: `BShit, Beefs, BigJoe, Boofers, DGreasy, DertyDer, Diarrhea, Ferrante, Gwon, JDM, Rut, Skrey, Swagga, Triz, Unks, wes11`

We'll need to know which one is "your" team (currently `'My Team'`). I'll make this configurable — likely `Skrey` based on the prior keeper list having José Ramírez, Rooker, Buxton, Seager, deGrom, Misiorowski.

### 2. Add positional eligibility to hitter data

Currently hitters have schema: `{name, type, pa, r, hr, rbi, so, tb, sb, obp}` with no position info.

**Approach**: In `create_league_stats.py` (which generates the HTML), join each hitter with the Fantrax CSV by player name to add an `eligiblePositions` array (e.g. `["LF","CF","RF","UT"]`). For pitchers, extract whether they're `SP`, `RP`, or `SP,RP` dual-eligible.

Name matching challenges (6 hitter mismatches, 2 pitcher mismatches):
- `Shohei Ohtani-H` (Fantrax) → `Shohei Ohtani` (projections) — special Fantrax naming for two-way player
- `Ronald Acuna Jr.` (Fantrax) → `Ronald Acuña Jr.` (projections) — accent difference
- `Agustin Ramirez` — not in projection pool (prospect)
- `Konnor Griffin` — not in projection pool (prospect)
- `Jeremy Pena` — not in projection pool (likely accent: `Jeremy Peña`)
- `Eugenio Suarez` — not in projection pool (likely accent: `Eugenio Suárez`)
- `Cristopher Sanchez` / `Eury Perez` — pitcher accent mismatches

**Solution**: Normalize names by stripping accents for matching. For `Ohtani-H`, special-case it. Players not in the projection pool (Griffin, Ramirez as prospects) won't have eligibility added — that's fine since they won't appear in the draft pool anyway.

### 3. Load keepers onto all 16 teams at startup

Currently `initKeepers()` only loads keepers for `'My Team'` and the list is hardcoded (and currently empty/commented out).

**New approach**: Build a `KEEPERS` data structure (keyed by team name) from the Fantrax Status column. At startup, iterate all teams and place each keeper into the appropriate roster slot:
- Hitter keepers → find the correct position slot (using their Fantrax position)
- SP keepers → fill SP slots
- RP keepers → fill RP slots
- Mark all keepers as drafted in `draftedPlayers`

For hitter slot assignment, use the player's primary (first listed) eligible position to pick the roster slot. If that slot is taken, try the next eligible position, then fall back to UTIL.

### 4. Display positional eligibility in the UI

Add eligibility info to the player list in the "Best Available" tab so during the draft you can see which positions a hitter can fill. This helps with draft decisions — e.g. knowing Cody Bellinger is `LF,CF,RF` eligible.

Show it as small badge(s) next to or under the player name in the available players list.

### 5. (Optional) Positional constraint on drafting

Currently when you draft a hitter, they go to the first empty hitter slot. With positional eligibility, we could enforce that a player can only fill slots matching their eligibility. This is a bigger change — the current tool treats all 9 hitter slots as interchangeable for marginal value calculation.

**Recommendation**: Start with just displaying eligibility (Steps 2-4). Positional drafting constraints can be a follow-up.

## Implementation Order

1. **Update `create_league_stats.py`** to read the Fantrax CSV and join positional eligibility onto hitters/pitchers when generating the HTML
2. **Update `TEAM_NAMES`** in the HTML to use Fantrax team names
3. **Build the keeper initialization** — generate a `KEEPERS` object from Fantrax data and load all teams' keepers at startup
4. **Update the UI** to display positional eligibility badges
5. **Regenerate `draft_tool.html`** with all the new data
