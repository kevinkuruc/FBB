#!/usr/bin/env python3
"""
Generate trade_tool.html from draft_tool.html + Post-Draft_Rosters.csv.

The trade tool is an in-season variant of the draft tool:
- All 16 rosters are pre-loaded from Post-Draft_Rosters.csv (not just keepers)
- Every owned player (and FA) stays in the "pool" as a potential trade target
- +MV column = wins gained if you ACQUIRED that player, assuming you drop your
  lowest-value current player they could replace (tried over every possible
  drop; we keep the best swap)
- Position filter lets you see e.g. "all 1B sorted by trade upside"

Re-run after roster moves: python3 build_trade_tool.py
"""

import csv
import json
import re
import unicodedata

ROSTERS_CSV = "/home/user/FBB/Post-Draft_Rosters.csv"
SRC_HTML = "/home/user/FBB/draft_tool.html"
OUT_HTML = "/home/user/FBB/trade_tool.html"

MY_TEAM = "Skrey"


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


def build_name_lookup(content):
    """Map normalized projection name -> exact projection name (with accents)."""
    lookup = {}
    for prefix in ['HITTERS_THEBAT = [', 'HITTERS_BATX = [', 'HITTERS_DC = [']:
        arr, _, _ = extract_json_array(content, prefix)
        for h in arr:
            lookup[normalize(h['name'])] = h['name']
    arr, _, _ = extract_json_array(content, 'const PITCHERS = [')
    for p in arr:
        lookup[normalize(p['name'])] = p['name']
    return lookup


def resolve_proj_name(fx_name, name_lookup):
    """Map a Fantrax player name to a projection-array name. Returns None if unmatched."""
    # Ohtani: projections use 'Shohei Ohtani' (the hitter); the SP entry has no
    # projection match unless we add one.
    if fx_name == 'Shohei Ohtani-H':
        return name_lookup.get(normalize('Shohei Ohtani'))
    if fx_name == 'Shohei Ohtani-P':
        return None
    return name_lookup.get(normalize(fx_name))


def load_rosters(name_lookup):
    """Read Post-Draft_Rosters.csv. Returns (rosters, owners).

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
    """Replace the initKeepers IIFE with one that loads full rosters and optimizes."""
    rosters_json = json.dumps(rosters, ensure_ascii=False, separators=(',', ':'))

    new_init = f"""(function initRosters() {{
        const ROSTERS = {rosters_json};

        Object.entries(ROSTERS).forEach(([teamName, players]) => {{
            const team = allTeams[teamName];
            if (!team) return;

            players.forEach(p => {{
                if (p.type === 'H') {{
                    const proj = getHitters().find(h => h.name === p.name);
                    if (proj) {{
                        const slotIdx = team.hitters.findIndex(s => s.player === null);
                        if (slotIdx !== -1) {{
                            team.hitters[slotIdx].player = {{ ...proj, type: 'H' }};
                            draftedPlayers.add(proj.name);
                        }}
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

            // Run the position optimizer so multi-eligible hitters end up in
            // the slots that don't waste their flexibility.
            optimizeTeamPositions(teamName);
        }});

        // Build the set of players currently on MY team — these can't be
        // trade targets (no point trading for someone you already have).
        const me = allTeams['{MY_TEAM}'];
        me.hitters.forEach(s => {{ if (s.player) myTeamPlayers.add(s.player.name); }});
        me.sps.forEach(p => {{ if (p) myTeamPlayers.add(p.name); }});
        me.rps.forEach(p => {{ if (p) myTeamPlayers.add(p.name); }});
    }})();"""

    pattern = r'\(function initKeepers\(\) \{.*?\}\)\(\);'
    new_content, n = re.subn(pattern, new_init, content, count=1, flags=re.DOTALL)
    if n != 1:
        raise RuntimeError("Could not find initKeepers() block to replace")
    return new_content


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
    """Replace calculateMarginalValue with trade-swap logic (optimal drop)."""
    new_fn = """function calculateMarginalValue(player) {
        const team = allTeams['Skrey'];
        const currentWins = getExpectedWins('Skrey').wins.TOTAL;
        let bestWins = currentWins;

        if (player.type === 'H') {
            // Save state: store current player in each slot
            const saved = team.hitters.map(s => s.player);
            const currentHitters = saved.filter(p => p !== null);

            // Build drop options: drop each current hitter (by index in currentHitters),
            // or drop nobody if a slot is open.
            const dropChoices = [];
            for (let i = 0; i < currentHitters.length; i++) dropChoices.push(i);
            if (currentHitters.length < team.hitters.length) dropChoices.push(-1);

            for (const dropIdx of dropChoices) {
                const newHitters = currentHitters
                    .filter((_, i) => i !== dropIdx)
                    .concat([player]);

                // Clear slots, place hitters, then run the position optimizer.
                team.hitters.forEach(s => { s.player = null; });
                newHitters.forEach(h => {
                    const slotIdx = team.hitters.findIndex(s => s.player === null);
                    if (slotIdx !== -1) team.hitters[slotIdx].player = h;
                });
                optimizeTeamPositions('Skrey');

                const w = getExpectedWins('Skrey').wins.TOTAL;
                if (w > bestWins) bestWins = w;
            }

            // Restore original slot assignments (saved positions are preserved
            // because we never modified the `position` field on slots).
            team.hitters.forEach((s, i) => { s.player = saved[i]; });
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

    print("Building name lookup from projection arrays...")
    name_lookup = build_name_lookup(content)
    print(f"  {len(name_lookup)} unique projection names")

    print("Loading rosters from Post-Draft_Rosters.csv...")
    rosters, owners = load_rosters(name_lookup)
    print(f"  {len(rosters)} teams, {sum(len(r) for r in rosters.values())} owned players placed")
    print(f"  {len(owners)} total players in pool (incl. FA)")

    print("Applying HTML patches...")
    content = patch_title_and_header(content)
    content = add_owner_badge_css(content)
    content = patch_tabs(content)
    content = add_owner_map_and_my_team_set(content, owners)
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
