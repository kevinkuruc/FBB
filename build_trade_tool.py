#!/usr/bin/env python3
"""
Generate trade_tool.html from draft_tool.html + the most recent projection /
roster files.

The trade tool is an in-season variant of the draft tool:
- Hitter projections come from Depth_Charts_May_ROS.csv (rest-of-season).
  Counting stats are supplemented to TARGET_PA at replacement rates so
  durability is baked in: a player projected for low ROS PA gets diluted
  toward replacement, while a healthy starter (>= TARGET_PA) is unchanged.
  The PER-PA rate × fixed PA/week framing is unchanged from the draft tool,
  so the math still produces sensible weekly numbers even with smaller
  ROS totals.
- All 16 rosters are pre-loaded from rosters_May.csv (not just keepers).
- Every owned player (and FA) stays in the "pool" as a potential trade target.
- +MV column = wins gained if you ACQUIRED that player. For hitters we try
  every possible drop from Skrey's roster and re-run the position optimizer,
  so a 1B target naturally lets Arraez slide to 2B (or wherever else his
  multi-position eligibility allows) — we keep whichever drop maximizes
  total wins.
- Position filter lets you see e.g. "all 1B sorted by trade upside".

Re-run after roster moves or new projections:
    python3 build_trade_tool.py
"""

import csv
import json
import re
import unicodedata

MAY_ROS_FILE = "/home/user/FBB/Depth_Charts_May_ROS.csv"
ROSTERS_CSV = "/home/user/FBB/rosters_May.csv"
SRC_HTML = "/home/user/FBB/draft_tool.html"
OUT_HTML = "/home/user/FBB/trade_tool.html"

MY_TEAM = "Skrey"

# Fantrax team names after the May rename (BShit -> Shmoulie).
TEAM_NAMES = [
    "Skrey", "JDM", "BigJoe", "Ferrante", "Rut", "Gwon", "Beefs", "Unks",
    "Swagga", "Triz", "Boofers", "Shmoulie", "DertyDer", "wes11",
    "DGreasy", "Diarrhea",
]

# ---- Hitter projection generation (mirrors create_league_stats.py) ----
# Filter: drop ROS projections below this PA (effectively bench bats / part-time).
MIN_PA = 100
# Supplement target: weekly stats are stat_total / NUM_WEEKS, so TARGET_PA / NUM_WEEKS
# is the assumed PA/week for a healthy starter. Keeping the draft-tool defaults
# (625 / 25 = 25 PA/week) means the weekly math is unchanged from draft time.
TARGET_PA = 625
NUM_WEEKS = 25
# Replacement per-PA rates (cohort: DC ranks 155-175 from create_league_stats.py).
REP_R_PER_PA = 0.121162
REP_HR_PER_PA = 0.033035
REP_RBI_PER_PA = 0.120773
REP_SO_PER_PA = 0.222623
REP_TB_PER_PA = 0.372522
REP_SB_PER_PA = 0.015157
REP_OBP = 0.324
# League constants used to compute a `value` field per hitter (a zTotal proxy)
# so the lineup optimizer can break position ties by fantasy value.
SD_R, SD_HR, SD_RBI, SD_SB, SD_SO, SD_TB, SD_OBP = 6.03, 2.93, 6.72, 2.57, 7.45, 15.94, 0.04
AVG_OBP = 0.327


def normalize(name):
    nfkd = unicodedata.normalize('NFKD', name)
    n = ''.join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()
    n = n.replace("'", "").replace("’", "").replace("-", " ").replace(".", "").replace(",", "")
    return ' '.join(n.split())


def extract_json_array(content, prefix):
    idx = content.find(prefix)
    if idx == -1:
        raise ValueError(f"Could not find '{prefix}'")
    start = content.find('[', idx)
    depth = 0
    end = start
    for i, c in enumerate(content[start:], start):
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
        if depth == 0:
            end = i + 1
            break
    return json.loads(content[start:end]), start, end


# ============================================================================
# Hitter projection pipeline (Depth_Charts_May_ROS.csv -> JS-ready dicts)
# ============================================================================

def compute_hitters_from_ros(positions_lookup):
    """Read May ROS depth-chart projections, supplement low-PA players to
    TARGET_PA at replacement rates, return a list of hitter dicts."""
    hitters = []
    skipped_low_pa = 0
    with open(MAY_ROS_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                pa = float(row['PA'])
                if pa < MIN_PA:
                    skipped_low_pa += 1
                    continue
                name = row['Name']
                k_pct = float(row['K%'])
                singles = float(row['1B'])
                doubles = float(row['2B'])
                triples = float(row['3B'])
                hr = float(row['HR'])
                runs = float(row['R'])
                rbi = float(row['RBI'])
                sb = float(row['SB'])
                obp = float(row['OBP'])

                so = k_pct * pa
                tb = singles + 2 * doubles + 3 * triples + 4 * hr

                if pa < TARGET_PA:
                    gap = TARGET_PA - pa
                    runs += gap * REP_R_PER_PA
                    hr += gap * REP_HR_PER_PA
                    rbi += gap * REP_RBI_PER_PA
                    so += gap * REP_SO_PER_PA
                    tb += gap * REP_TB_PER_PA
                    sb += gap * REP_SB_PER_PA
                    obp = (pa * obp + gap * REP_OBP) / TARGET_PA
                    pa = TARGET_PA

                # Per-category z-scores -> zTotal. Mirrors create_league_stats.py.
                z_r = (runs / NUM_WEEKS) / SD_R
                z_hr = (hr / NUM_WEEKS) / SD_HR
                z_rbi = (rbi / NUM_WEEKS) / SD_RBI
                z_sb = (sb / NUM_WEEKS) / SD_SB
                z_tb = (tb / NUM_WEEKS) / SD_TB
                z_so = -(so / NUM_WEEKS) / SD_SO
                z_obp = (obp - AVG_OBP) / 9 / SD_OBP
                value = z_r + z_hr + z_rbi + z_sb + z_tb + z_so + z_obp

                hitters.append({
                    'name': name,
                    'type': 'H',
                    'pa': int(round(pa)),
                    'r': int(round(runs)),
                    'hr': int(round(hr)),
                    'rbi': int(round(rbi)),
                    'so': int(round(so)),
                    'tb': int(round(tb)),
                    'sb': int(round(sb)),
                    'obp': round(obp, 3),
                    'pos': positions_lookup.get(normalize(name), []),
                    'value': round(value, 4),
                })
            except (ValueError, KeyError):
                continue
    print(f"  May ROS: kept {len(hitters)} hitters, skipped {skipped_low_pa} below MIN_PA={MIN_PA}")
    return hitters


def build_positions_lookup():
    """Map normalized player name -> list of hitter-eligible positions from
    rosters_May.csv. Skips pitcher positions; keeps first occurrence (lowest
    RkOv, which is the MLB player rather than a name-collision minor leaguer)."""
    lookup = {}
    seen = set()
    HITTER_SLOTS = ('C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'UT')
    with open(ROSTERS_CSV) as f:
        for row in csv.DictReader(f):
            n = normalize(row['Player'])
            if n in seen:
                continue
            seen.add(n)
            positions = [p for p in row['Position'].split(',') if p in HITTER_SLOTS]
            if positions:
                lookup[n] = positions
    return lookup


def replace_hitter_arrays(content, hitters):
    """Replace HITTERS_THEBAT / HITTERS_BATX / HITTERS_DC with the new May ROS
    array. Only DC projections were refreshed for May, so all three slots get
    the same data — the projection toggle in the UI becomes a no-op but it's
    harmless to leave."""
    new_json = json.dumps(hitters, ensure_ascii=False, separators=(',', ':'))
    for prefix in ['HITTERS_THEBAT = [', 'HITTERS_BATX = [', 'HITTERS_DC = [']:
        _, start, end = extract_json_array(content, prefix)
        content = content[:start] + new_json + content[end:]
    return content


def replace_team_names(content):
    """Update the embedded TEAM_NAMES array (BShit -> Shmoulie this cycle)."""
    pattern = r"const TEAM_NAMES = \[.*?\];"
    new_value = f"const TEAM_NAMES = {json.dumps(TEAM_NAMES)};"
    return re.sub(pattern, new_value, content)


def build_name_lookup(content):
    """Map normalized projection name -> exact projection name (with accents),
    used to translate Fantrax-CSV names into the embedded projection names."""
    lookup = {}
    for prefix in ['HITTERS_THEBAT = [', 'HITTERS_BATX = [', 'HITTERS_DC = [']:
        arr, _, _ = extract_json_array(content, prefix)
        for h in arr:
            lookup[normalize(h['name'])] = h['name']
    arr, _, _ = extract_json_array(content, 'const PITCHERS = [')
    for p in arr:
        lookup[normalize(p['name'])] = p['name']
    return lookup


# ============================================================================
# Roster loading (CSV -> JS structures)
# ============================================================================

def resolve_proj_name(fx_name, name_lookup):
    """Map a Fantrax player name to a projection-array name. Returns None if unmatched."""
    if fx_name == 'Shohei Ohtani-H':
        return name_lookup.get(normalize('Shohei Ohtani'))
    if fx_name == 'Shohei Ohtani-P':
        return None
    return name_lookup.get(normalize(fx_name))


def load_rosters(name_lookup):
    """Read rosters_May.csv. Returns (rosters, owners).

    rosters: {team_name: [{name, type, position?}]} for placing on teams
    owners:  {proj_name: team_name or 'FA'} for display in trade-target list

    The CSV is sorted by RkOv ascending and contains duplicate names (the MLB
    star + minor-leaguers sharing a name). We keep the FIRST occurrence of each
    projection-mapped name, which corresponds to the MLB player.
    """
    rosters = {}
    owners = {}
    skipped = []
    seen = set()
    with open(ROSTERS_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            fx_name = row['Player']
            team = row['Status']
            pos = row['Position']

            proj_name = resolve_proj_name(fx_name, name_lookup)
            if not proj_name:
                if team != 'FA':
                    skipped.append((fx_name, team))
                continue

            if proj_name in seen:
                continue
            seen.add(proj_name)

            owners[proj_name] = team
            if team == 'FA':
                continue

            positions = pos.split(',')
            has_batting = any(p in ('C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'UT') for p in positions)
            has_pitching = any(p in ('SP', 'RP') for p in positions)

            if has_pitching and not has_batting:
                ptype = 'SP' if 'SP' in positions else 'RP'
                entry = {'name': proj_name, 'type': ptype}
            else:
                entry = {'name': proj_name, 'type': 'H', 'position': pos}

            rosters.setdefault(team, []).append(entry)

    if skipped:
        print(f"  Skipped {len(skipped)} owned players not in projections (prospects, two-way pitcher):")
        for n, t in skipped[:10]:
            print(f"    {n} ({t})")
        if len(skipped) > 10:
            print(f"    ... and {len(skipped) - 10} more")

    return rosters, owners


# ============================================================================
# HTML / JS PATCHES
# ============================================================================

def patch_title_and_header(content):
    content = content.replace(
        '<title>Fantasy Baseball Draft Tool</title>',
        '<title>Fantasy Baseball Trade Analysis</title>'
    )
    content = content.replace(
        '<h1>Fantasy Baseball Draft Tool 2026</h1>',
        '<h1>Fantasy Baseball Trade Analysis 2026</h1>'
    )
    content = content.replace(
        '<p class="subtitle">Marginal Win Probability Analysis | 14 Categories</p>',
        '<p class="subtitle">Δ Expected Wins from Acquiring a Player | Optimal Drop Assumed</p>'
    )
    return content


def patch_tabs(content):
    """Rename 'Best Available' to 'Trade Targets', remove 'Draft Log' tab/panel."""
    content = content.replace(
        '<button class="tab" onclick="showTab(\'available\')">Best Available</button>',
        '<button class="tab" onclick="showTab(\'available\')">Trade Targets</button>'
    )
    content = re.sub(
        r'\s*<button class="tab" onclick="showTab\(\'log\'\)">Draft Log</button>\n',
        '\n',
        content
    )
    content = re.sub(
        r'\s*<!-- Draft Log Panel -->\s*<div id="log-panel" class="panel">\s*<div id="draft-log" class="draft-log"></div>\s*</div>',
        '',
        content
    )
    return content


def replace_keepers_with_rosters(content, rosters):
    """Replace the initKeepers IIFE with one that loads full rosters and
    selects the best 9 active hitters (rest go to benchHitters)."""
    rosters_json = json.dumps(rosters, ensure_ascii=False, separators=(',', ':'))

    new_init = f"""(function initRosters() {{
        const ROSTERS = {rosters_json};

        Object.entries(ROSTERS).forEach(([teamName, players]) => {{
            const team = allTeams[teamName];
            if (!team) return;

            // Stage every hitter onto the bench first; the optimizer then picks
            // the best 9 to be active and leaves the rest as bench. This is
            // smarter than the old "first 9 by CSV order" loader, which could
            // exclude a critical position player (e.g. the only catcher).
            team.benchHitters = team.benchHitters || [];

            players.forEach(p => {{
                if (p.type === 'H') {{
                    const proj = getHitters().find(h => h.name === p.name);
                    if (proj) {{
                        team.benchHitters.push({{ ...proj, type: 'H' }});
                        draftedPlayers.add(proj.name);
                    }}
                }} else if (p.type === 'SP') {{
                    const proj = PITCHERS.find(x => x.name === p.name);
                    if (proj) {{
                        const slotIdx = team.sps.findIndex(s => s === null);
                        if (slotIdx !== -1) {{
                            team.sps[slotIdx] = proj;
                            draftedPlayers.add(proj.name);
                        }}
                    }}
                }} else if (p.type === 'RP') {{
                    const proj = PITCHERS.find(x => x.name === p.name);
                    if (proj) {{
                        const slotIdx = team.rps.findIndex(s => s === null);
                        if (slotIdx !== -1) {{
                            team.rps[slotIdx] = proj;
                            draftedPlayers.add(proj.name);
                        }}
                    }}
                }}
            }});

            optimizeTeamPositions(teamName);
        }});

        // Build the set of players currently on MY team (active + bench) —
        // these can't be trade targets (no point trading for someone we have).
        const me = allTeams['{MY_TEAM}'];
        me.hitters.forEach(s => {{ if (s.player) myTeamPlayers.add(s.player.name); }});
        me.benchHitters.forEach(p => myTeamPlayers.add(p.name));
        me.sps.forEach(p => {{ if (p) myTeamPlayers.add(p.name); }});
        me.rps.forEach(p => {{ if (p) myTeamPlayers.add(p.name); }});
    }})();"""

    pattern = r'\(function initKeepers\(\) \{.*?\}\)\(\);'
    new_content, n = re.subn(pattern, new_init, content, count=1, flags=re.DOTALL)
    if n != 1:
        raise RuntimeError("Could not find initKeepers() block to replace")
    return new_content


def replace_optimizer(content):
    """Replace optimizeTeamPositions with a version that:
    - Pools active+bench hitters and picks the best 9 active
    - Sorts most-constrained-first; ties broken by `value` (zTotal proxy) DESC
    - Two-pass placement: non-UTIL first, then UTIL for unplaced
    - Players who don't fit any eligible slot go to benchHitters (no last-resort
      placement into ineligible slots)"""
    new_fn = """function optimizeTeamPositions(teamName) {
        const team = allTeams[teamName];
        if (!team.benchHitters) team.benchHitters = [];

        // Pool = currently active + currently benched.
        const pool = [];
        team.hitters.forEach(slot => { if (slot.player) pool.push(slot.player); });
        pool.push(...team.benchHitters);

        // Clear active slots and bench; we'll reassign from scratch.
        team.hitters.forEach(s => { s.player = null; });
        team.benchHitters = [];

        if (pool.length === 0) return;

        // Build eligibility per player. UTIL counts as a 10th eligibility for
        // any hitter with at least one defined position.
        const elig = pool.map(player => {
            const pos = player.pos || [];
            const nonUtil = HITTER_POSITIONS.filter(s => s !== 'UTIL' && pos.includes(s));
            const canUtil = pos.length > 0;
            return {
                player,
                nonUtil,
                canUtil,
                eligCount: nonUtil.length + (canUtil ? 1 : 0),
                value: typeof player.value === 'number' ? player.value : 0,
            };
        });

        // Most-constrained-first (a C-only player goes before a 1B/3B player),
        // with `value` DESC as the tie-breaker — when two players have the same
        // number of eligible slots, the better fantasy bat gets first pick.
        elig.sort((a, b) => {
            if (a.eligCount !== b.eligCount) return a.eligCount - b.eligCount;
            return b.value - a.value;
        });

        // For each player with multi-slot eligibility, prefer the RARER slot
        // (the one fewest other pool players can fill). This avoids Arraez
        // (1B/2B) parking at 1B when 2B has no other claimants.
        const slotDemand = {};
        for (const e of elig) {
            for (const s of e.nonUtil) slotDemand[s] = (slotDemand[s] || 0) + 1;
        }
        for (const e of elig) {
            e.nonUtil.sort((a, b) => slotDemand[a] - slotDemand[b]);
        }

        // Pass 1: place each player in their first available NON-UTIL eligible
        // slot (rarity-sorted). Players who can't fit any position-specific
        // slot fall through to pass 2.
        const placed = new Set();
        elig.forEach((e, idx) => {
            for (const pos of e.nonUtil) {
                const slotIdx = team.hitters.findIndex(s => s.position === pos && s.player === null);
                if (slotIdx !== -1) {
                    team.hitters[slotIdx].player = e.player;
                    placed.add(idx);
                    break;
                }
            }
        });

        // Pass 2: UTIL goes to the highest-value unplaced player (value DESC).
        const unplaced = elig
            .map((e, idx) => ({ e, idx }))
            .filter(({ idx }) => !placed.has(idx))
            .sort((a, b) => b.e.value - a.e.value);
        for (const { e, idx } of unplaced) {
            if (!e.canUtil) continue;
            const slotIdx = team.hitters.findIndex(s => s.position === 'UTIL' && s.player === null);
            if (slotIdx === -1) break;
            team.hitters[slotIdx].player = e.player;
            placed.add(idx);
        }

        // Pass 3: everyone still unplaced goes to bench. Order doesn't matter
        // for scoring, but keep it value-DESC so the UI display is stable.
        elig
            .map((e, idx) => ({ e, idx }))
            .filter(({ idx }) => !placed.has(idx))
            .sort((a, b) => b.e.value - a.e.value)
            .forEach(({ e }) => team.benchHitters.push(e.player));
    }"""

    pattern = r'function optimizeTeamPositions\(teamName\) \{.*?\n    \}'
    new_content, n = re.subn(pattern, new_fn, content, count=1, flags=re.DOTALL)
    if n != 1:
        raise RuntimeError("Could not find optimizeTeamPositions to replace")
    return new_content


def add_bench_to_team_init(content):
    """Add benchHitters: [] to each team's initialization object."""
    return content.replace(
        "rps: Array(RP_SLOTS).fill(null)",
        "rps: Array(RP_SLOTS).fill(null),\n            benchHitters: []",
        1,
    )


def add_bench_section_to_my_roster(content):
    """Surface the benchHitters list in the My Roster view so the user can see
    who's currently inactive (e.g. Moniak when Moreno wins the C slot)."""
    # Add a placeholder div in the HTML markup after the RP section.
    markup_old = '<div id="rp-roster" class="roster-grid pitchers"></div>\n            </div>'
    markup_new = (
        '<div id="rp-roster" class="roster-grid pitchers"></div>\n            </div>\n'
        '            <div class="roster-section" id="bench-section" style="display: none;">\n'
        '                <h3>Bench (not contributing to active stats)</h3>\n'
        '                <div id="bench-roster" class="roster-grid"></div>\n'
        '            </div>'
    )
    if markup_old not in content:
        raise RuntimeError("Could not find RP roster markup to anchor bench section")
    content = content.replace(markup_old, markup_new, 1)

    # In renderRoster, populate the bench list right after the RP section.
    js_marker = "// Category tables\n        const { hittingProj, pitchingProj, wins } = getExpectedWins('Skrey');"
    js_new = (
        "// Bench (inactive hitters)\n"
        "        const bench = team.benchHitters || [];\n"
        "        const benchSection = document.getElementById('bench-section');\n"
        "        if (bench.length === 0) {\n"
        "            benchSection.style.display = 'none';\n"
        "        } else {\n"
        "            benchSection.style.display = 'block';\n"
        "            document.getElementById('bench-roster').innerHTML = bench.map(p => `\n"
        "                <div class=\"roster-slot filled\">\n"
        "                    <div class=\"position\">BENCH</div>\n"
        "                    <div class=\"player-name\">${p.name}</div>\n"
        "                    ${p.pos && p.pos.length ? `<div style=\"margin: 2px 0\">${p.pos.map(x => '<span class=\"pos-badge\">' + x + '</span>').join(' ')}</div>` : ''}\n"
        "                    <div class=\"player-stats\">R:${p.r} HR:${p.hr} RBI:${p.rbi} SB:${p.sb} OBP:${p.obp.toFixed(3)}</div>\n"
        "                </div>\n"
        "            `).join('');\n"
        "        }\n\n"
        "        // Category tables\n        const { hittingProj, pitchingProj, wins } = getExpectedWins('Skrey');"
    )
    if js_marker not in content:
        raise RuntimeError("Could not find renderRoster anchor for bench injection")
    return content.replace(js_marker, js_new, 1)


def add_owner_map_and_my_team_set(content, owners):
    """Add OWNER_MAP and myTeamPlayers Set before initRosters runs."""
    owner_json = json.dumps(owners, ensure_ascii=False, separators=(',', ':'))
    insertion = f"""
    // =============================================================================
    // TRADE TOOL DATA: owner of each player + set of players on MY team
    // =============================================================================
    const OWNER_MAP = {owner_json};
    const myTeamPlayers = new Set();

    """
    # Insert right before "let draftLog ="
    marker = "    let draftLog = [];"
    if marker not in content:
        raise RuntimeError("Could not find draftLog declaration")
    return content.replace(marker, insertion + marker, 1)


def replace_marginal_value(content):
    """Replace calculateMarginalValue with trade-swap logic (optimal drop).

    Drop candidates include both active AND benched hitters — trading away a
    benched player is a real option (and the trade target may then push another
    active player off the lineup)."""
    new_fn = """function calculateMarginalValue(player) {
        const team = allTeams['Skrey'];
        const currentWins = getExpectedWins('Skrey').wins.TOTAL;
        let bestWins = currentWins;

        if (player.type === 'H') {
            // Snapshot active slots + bench so we can restore exactly.
            const savedActive = team.hitters.map(s => s.player);
            const savedBench = [...team.benchHitters];
            const allHitters = [...savedActive.filter(p => p !== null), ...savedBench];

            // Drop options: each current hitter (active or bench), or no drop
            // if the team has fewer than 9 hitters total.
            const dropChoices = [...allHitters];
            if (allHitters.length < team.hitters.length) dropChoices.push(null);

            for (const dropPlayer of dropChoices) {
                const newPool = allHitters
                    .filter(h => h !== dropPlayer)
                    .concat([player]);

                // Stage everyone on the bench and let optimizeTeamPositions pick
                // the best active 9. This naturally handles position scarcity —
                // a 1B target with Arraez (1B/2B) on roster won't waste 2B.
                team.hitters.forEach(s => { s.player = null; });
                team.benchHitters = newPool;
                optimizeTeamPositions('Skrey');

                const w = getExpectedWins('Skrey').wins.TOTAL;
                if (w > bestWins) bestWins = w;
            }

            // Restore original state.
            team.hitters.forEach((s, i) => { s.player = savedActive[i]; });
            team.benchHitters = savedBench;
        } else if (player.type === 'SP') {
            const saved = [...team.sps];
            for (let i = 0; i < team.sps.length; i++) {
                team.sps[i] = player;
                const w = getExpectedWins('Skrey').wins.TOTAL;
                if (w > bestWins) bestWins = w;
                team.sps[i] = saved[i];
            }
        } else if (player.type === 'RP') {
            const saved = [...team.rps];
            for (let i = 0; i < team.rps.length; i++) {
                team.rps[i] = player;
                const w = getExpectedWins('Skrey').wins.TOTAL;
                if (w > bestWins) bestWins = w;
                team.rps[i] = saved[i];
            }
        }

        return bestWins - currentWins;
    }"""

    pattern = r'function calculateMarginalValue\(player\) \{.*?\n    \}'
    new_content, n = re.subn(pattern, new_fn, content, count=1, flags=re.DOTALL)
    if n != 1:
        raise RuntimeError("Could not find calculateMarginalValue to replace")
    return new_content


def patch_available_filter_and_clicks(content):
    """
    In renderAvailablePlayers:
      - Replace the `!draftedPlayers.has(p.name)` filter with `!myTeamPlayers.has(p.name)`
        so the pool stays full but excludes players we already have.
      - Replace player-row onclick handlers with no-ops (no drafting in trade tool).
      - Inject an owner badge next to the player name in each row.
    """
    # Filter change: only the line inside renderAvailablePlayers
    content = content.replace(
        '.filter(p => !draftedPlayers.has(p.name))',
        '.filter(p => !myTeamPlayers.has(p.name))'
    )

    # Replace the pitcher row onclick (draftToSlot + openDraftModal) with no-op
    content = re.sub(
        r'onclick="if\(!draftToSlot\(PITCHERS\.find\(x=>x\.name===\'\$\{p\.name\.replace\(/\'\/g, "\\\\\'"\)\}\'\)\)\)\{openDraftModal\(\'\$\{p\.name\.replace\(/\'\/g, "\\\\\'"\)\}\', \'\$\{p\.type\}\'\)\}"',
        '',
        content
    )
    # Replace the hitter row onclick
    content = re.sub(
        r'onclick="if\(!draftToSlot\(\{\.\.\.getHitters\(\)\.find\(x=>x\.name===\'\$\{p\.name\.replace\(/\'\/g, "\\\\\'"\)\}\'\)\, type:\'H\'\}\)\)\{openDraftModal\(\'\$\{p\.name\.replace\(/\'\/g, "\\\\\'"\)\}\', \'H\'\)\}"',
        '',
        content
    )

    # Inject owner badge into the player name cells.
    # For pitcher rows, the name cell is:
    #   <div>${p.name}${p.dualEligible ? ... : ''}</div>
    # Append the owner badge after the existing badges.
    content = content.replace(
        "<div>${p.name}${p.dualEligible ? '<span class=\"pos-badges\"><span class=\"pos-badge\">SP/RP</span></span>' : ''}</div>",
        "<div>${p.name}${p.dualEligible ? '<span class=\"pos-badges\"><span class=\"pos-badge\">SP/RP</span></span>' : ''}<span class=\"owner-badge\">${OWNER_MAP[p.name] || 'FA'}</span></div>"
    )
    # For hitter rows:
    content = content.replace(
        "<div>${p.name}${p.pos && p.pos.length ? '<span class=\"pos-badges\">' + p.pos.map(pos => '<span class=\"pos-badge\">' + pos + '</span>').join('') + '</span>' : ''}</div>",
        "<div>${p.name}${p.pos && p.pos.length ? '<span class=\"pos-badges\">' + p.pos.map(pos => '<span class=\"pos-badge\">' + pos + '</span>').join('') + '</span>' : ''}<span class=\"owner-badge\">${OWNER_MAP[p.name] || 'FA'}</span></div>"
    )
    return content


def disable_roster_slot_clicks(content):
    """In renderRoster, empty slots currently say 'Click to draft' and have an onclick
    that opens the Best Available tab. In trade tool there's no draft — replace
    with an em-dash and remove the click handlers."""
    # Hitter empty slot
    content = content.replace(
        '${!filled ? `onclick="selectSlotForDraft(\'hitter\', ${idx})"` : \'\'} style="${!filled ? \'cursor: pointer;\' : \'\'}"',
        '',
        # only-once replacement is fine since these are unique strings per slot type
    )
    # Above replaces *all* three occurrences (hitter, sp, rp) because the snippet
    # only differs in the slotType. We need to do each separately:
    content = content.replace(
        '${!filled ? `onclick="selectSlotForDraft(\'sp\', ${idx})"` : \'\'} style="${!filled ? \'cursor: pointer;\' : \'\'}"',
        ''
    )
    content = content.replace(
        '${!filled ? `onclick="selectSlotForDraft(\'rp\', ${idx})"` : \'\'} style="${!filled ? \'cursor: pointer;\' : \'\'}"',
        ''
    )
    content = content.replace(
        "${filled ? player.name : 'Click to draft'}",
        "${filled ? player.name : '—'}"
    )
    return content


def patch_renderAll(content):
    """renderAll calls renderDraftLog which no longer exists. Strip those calls."""
    # Strip the showTab handler line for 'log' (must run before the bare
    # renderDraftLog() pattern so we don't leave a dangling `if (...)`).
    content = re.sub(
        r"\s*if \(tabName === 'log'\) renderDraftLog\(\);",
        '',
        content,
    )
    # And the standalone renderDraftLog() inside renderAll().
    content = re.sub(r'\n\s*renderDraftLog\(\);', '', content)
    return content


def add_owner_badge_css(content):
    """Inject CSS for the new owner badge."""
    css = """
        .owner-badge {
            display: inline-block;
            margin-left: 6px;
            padding: 1px 5px;
            font-size: 9px;
            border-radius: 3px;
            background: #3d2d5a;
            color: #c8a8e0;
            font-weight: bold;
            letter-spacing: 0.5px;
        }
"""
    marker = "        .pos-badges { display: inline; margin-left: 6px; }"
    return content.replace(marker, css + marker, 1)


def main():
    print("Reading draft_tool.html...")
    with open(SRC_HTML) as f:
        content = f.read()

    print("Building position-eligibility lookup from rosters_May.csv...")
    positions_lookup = build_positions_lookup()
    print(f"  {len(positions_lookup)} players with hitter eligibility")

    print("Computing May ROS hitter projections...")
    hitters = compute_hitters_from_ros(positions_lookup)

    print("Replacing embedded HITTERS arrays and TEAM_NAMES...")
    content = replace_hitter_arrays(content, hitters)
    content = replace_team_names(content)

    # Name lookup must run AFTER the hitter arrays were swapped to May ROS,
    # otherwise we'd map names against the stale March projection list.
    print("Building name lookup from updated projection arrays...")
    name_lookup = build_name_lookup(content)
    print(f"  {len(name_lookup)} unique projection names")

    print(f"Loading rosters from {ROSTERS_CSV}...")
    rosters, owners = load_rosters(name_lookup)
    print(f"  {len(rosters)} teams, {sum(len(r) for r in rosters.values())} owned players placed")
    print(f"  {len(owners)} total players in pool (incl. FA)")

    print("Applying HTML patches...")
    content = patch_title_and_header(content)
    content = add_owner_badge_css(content)
    content = patch_tabs(content)
    content = add_owner_map_and_my_team_set(content, owners)
    content = add_bench_to_team_init(content)
    content = add_bench_section_to_my_roster(content)
    content = replace_optimizer(content)
    content = replace_keepers_with_rosters(content, rosters)
    content = replace_marginal_value(content)
    content = patch_available_filter_and_clicks(content)
    content = disable_roster_slot_clicks(content)
    content = patch_renderAll(content)

    print(f"Writing {OUT_HTML}...")
    with open(OUT_HTML, 'w') as f:
        f.write(content)
    print("Done!")


if __name__ == '__main__':
    main()
