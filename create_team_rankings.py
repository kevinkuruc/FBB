#!/usr/bin/env python3
"""
Creates two new tools from the draft_tool.html template and Post-Draft_Rosters.csv:

1. team_rankings.html ("Team Rankings")
   - Exact replica of the draft tool structure
   - All post-draft roster players loaded as "keepers" (identical to how keeper
     data was previously embedded via add_fantrax_data.py)
   - Players still available for drafting to empty roster slots
   - Preserves draft-time view so you can revisit it

2. in_season_rankings.html ("In Season Rankings")
   - All teams fully filled with their best 9 hitters optimally placed
   - Skrey's C slot left empty as the target slot for free agent evaluation
   - Free agents ranked by marginal value (how much they'd help in the C slot)
   - Position optimizer runs for ALL teams including Skrey

How roster data is loaded (identical to keeper initialization in add_fantrax_data.py):
   - Post-Draft_Rosters.csv is read (same format as Fantrax-Players export)
   - Each non-FA player is matched to projection data by normalized name
   - Hitters get {name, type:'H', position} entries
   - Pitchers get {name, type:'SP'|'RP'} entries
   - The KEEPERS/ROSTERS JSON is embedded in an initKeepers() IIFE
   - At startup, each player is placed on their team:
     * Hitters: try matching position slot → UTIL fallback → any empty slot
     * SP/RP: fill first available slot of that type
   - optimizeTeamPositions() runs for each team after loading
"""

import csv
import json
import re
import unicodedata

ROSTER_FILE = "/home/user/FBB/Post-Draft_Rosters.csv"
HTML_FILE = "/home/user/FBB/draft_tool.html"
TEAM_RANKINGS_OUT = "/home/user/FBB/team_rankings.html"
IN_SEASON_OUT = "/home/user/FBB/in_season_rankings.html"


def normalize(name):
    """Strip accents, punctuation, and normalize whitespace for name matching."""
    nfkd = unicodedata.normalize('NFKD', name)
    n = ''.join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()
    n = n.replace("'", "").replace("\u2019", "").replace("-", " ").replace(".", "").replace(",", "")
    return ' '.join(n.split())


def extract_json_array(content, prefix):
    """Extract a JSON array from the HTML given a variable assignment prefix."""
    idx = content.find(prefix)
    if idx == -1:
        raise ValueError(f"Could not find '{prefix}' in HTML")
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


def build_proj_name_lookup(content):
    """Build normalized name -> projection name lookup from all data arrays."""
    all_proj_names = {}
    for prefix in ['HITTERS_THEBAT = [', 'HITTERS_BATX = [', 'HITTERS_DC = [']:
        arr, _, _ = extract_json_array(content, prefix)
        for h in arr:
            all_proj_names[normalize(h['name'])] = h['name']
    arr, _, _ = extract_json_array(content, 'const PITCHERS = [')
    for p in arr:
        all_proj_names[normalize(p['name'])] = p['name']
    # Ohtani special case
    all_proj_names[normalize('Shohei Ohtani-H')] = all_proj_names.get(
        normalize('Shohei Ohtani'), 'Shohei Ohtani')
    return all_proj_names


def build_rosters_from_csv(all_proj_names):
    """
    Build rosters dict from Post-Draft_Rosters.csv.
    Identical structure to how add_fantrax_data.py builds keepers:
    { teamName: [ {name, type, position?}, ... ] }
    """
    rosters = {}
    with open(ROSTER_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['Status'] == 'FA':
                continue
            team = row['Status']
            if team not in rosters:
                rosters[team] = []

            fx_name = row['Player']
            pos = row['Position']
            positions = pos.split(',')
            has_batting = any(p in ('C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'UT')
                            for p in positions)
            has_pitching = any(p in ('SP', 'RP') for p in positions)

            # Resolve to projection name
            n = normalize(fx_name)
            proj_name = all_proj_names.get(n)
            if not proj_name:
                # Special case Ohtani hitter
                if fx_name == 'Shohei Ohtani-H':
                    proj_name = all_proj_names.get(normalize('Shohei Ohtani'))
                if not proj_name:
                    print(f"  WARNING: '{fx_name}' ({team}) not found in projections, skipping")
                    continue

            if has_pitching and not has_batting:
                ptype = 'SP' if 'SP' in positions else 'RP'
                rosters[team].append({'name': proj_name, 'type': ptype})
            else:
                rosters[team].append({'name': proj_name, 'type': 'H', 'position': pos})

    return rosters


def embed_rosters(content, rosters_data, label="ROSTERS"):
    """
    Replace the initKeepers() function with one that loads all teams' rosters.
    Documentation comment explains the data source and loading process.
    """
    rosters_json = json.dumps(rosters_data, ensure_ascii=False, separators=(',', ':'))

    new_init = f"""(function initKeepers() {{
        // {label} - loaded from Post-Draft_Rosters.csv via create_team_rankings.py
        // Identical to how keeper data was previously embedded via add_fantrax_data.py:
        //   1. CSV is read; each non-FA player matched to projection data by normalized name
        //   2. Hitters get {{name, type:'H', position}} entries
        //   3. Pitchers get {{name, type:'SP'|'RP'}} entries
        //   4. At startup, players placed on teams:
        //      - Hitters: try matching position slot -> UTIL fallback -> any empty slot
        //      - SP/RP: fill first available slot of that type
        //   5. optimizeTeamPositions() runs for each team after loading
        const KEEPERS = {rosters_json};

        Object.entries(KEEPERS).forEach(([teamName, keepers]) => {{
            const team = allTeams[teamName];
            if (!team) return;

            keepers.forEach(keeper => {{
                if (keeper.type === 'H') {{
                    const player = getHitters().find(h => h.name === keeper.name);
                    if (player) {{
                        // Try to place in a matching position slot
                        const eligiblePositions = keeper.position ? keeper.position.split(',') : [];
                        let slotIdx = -1;
                        for (const pos of eligiblePositions) {{
                            slotIdx = team.hitters.findIndex(s => s.position === pos && s.player === null);
                            if (slotIdx !== -1) break;
                        }}
                        // Fall back to UTIL
                        if (slotIdx === -1) {{
                            slotIdx = team.hitters.findIndex(s => s.position === 'UTIL' && s.player === null);
                        }}
                        // Last resort: any empty slot
                        if (slotIdx === -1) {{
                            slotIdx = team.hitters.findIndex(s => s.player === null);
                        }}
                        if (slotIdx !== -1) {{
                            team.hitters[slotIdx].player = {{ ...player, type: 'H' }};
                            draftedPlayers.add(player.name);
                            draftLog.push({{ player: player.name, team: teamName, type: 'H' }});
                        }}
                    }}
                }} else if (keeper.type === 'SP') {{
                    const player = PITCHERS.find(p => p.name === keeper.name);
                    if (player) {{
                        const slotIdx = team.sps.findIndex(s => s === null);
                        if (slotIdx !== -1) {{
                            team.sps[slotIdx] = player;
                            draftedPlayers.add(player.name);
                            draftLog.push({{ player: player.name, team: teamName, type: 'SP' }});
                        }}
                    }}
                }} else if (keeper.type === 'RP') {{
                    const player = PITCHERS.find(p => p.name === keeper.name);
                    if (player) {{
                        const slotIdx = team.rps.findIndex(s => s === null);
                        if (slotIdx !== -1) {{
                            team.rps[slotIdx] = player;
                            draftedPlayers.add(player.name);
                            draftLog.push({{ player: player.name, team: teamName, type: 'RP' }});
                        }}
                    }}
                }}
            }});
        }});

        // Optimize position assignments for all teams
        TEAM_NAMES.forEach(teamName => optimizeTeamPositions(teamName));
    }})();"""

    # Replace the old initKeepers block
    pattern = r'\(function initKeepers\(\) \{.*?\}\)\(\);'
    content = re.sub(pattern, new_init, content, flags=re.DOTALL)
    return content


def create_team_rankings(content, rosters_data):
    """
    Create team_rankings.html: exact replica of draft tool with all post-draft
    roster players pre-loaded as keepers. Title changed to 'Team Rankings'.
    """
    # Change title and heading
    content = content.replace(
        '<title>Fantasy Baseball Draft Tool</title>',
        '<title>Team Rankings</title>'
    )
    content = content.replace(
        'Fantasy Baseball Draft Tool 2026',
        'Team Rankings 2026'
    )

    # Embed all roster players as keepers
    content = embed_rosters(content, rosters_data,
                           label="POST-DRAFT ROSTERS")

    return content


def create_in_season_rankings(content, rosters_data):
    """
    Create in_season_rankings.html: all teams fully filled, Skrey's C slot
    left empty. Free agents ranked by marginal value for that slot.

    Key differences from team_rankings:
    - Title: "In Season Rankings"
    - All teams' lineups optimized with best 9 hitters
    - Skrey has 8 hitters filled + C empty (the evaluation target)
    - calculateMarginalValue evaluates players ONLY for the C slot
    - Position optimizer runs for Skrey too
    """
    # Change title and heading
    content = content.replace(
        '<title>Fantasy Baseball Draft Tool</title>',
        '<title>In Season Rankings</title>'
    )
    content = content.replace(
        'Fantasy Baseball Draft Tool 2026',
        'In Season Rankings 2026'
    )

    # Embed all roster players as keepers
    content = embed_rosters(content, rosters_data,
                           label="IN-SEASON ROSTERS")

    # Modify calculateMarginalValue to evaluate for C slot specifically.
    # In the draft tool, it finds "first empty slot" - we need it to try
    # the C slot specifically for hitters, since that's Skrey's empty spot.
    # For the in-season tool, we also need to substitute OUT the worst
    # starter and substitute IN the candidate to find the marginal value
    # of picking up a free agent.
    #
    # The approach: for hitters, temporarily place in C slot (index 0).
    # For pitchers, still find first empty slot (there may be none).
    old_marginal = """function calculateMarginalValue(player) {
        const team = allTeams['Skrey'];
        const currentWins = getExpectedWins('Skrey').wins.TOTAL;
        let newWins;

        if (player.type === 'H') {
            // Hitter: find first empty slot
            const emptyIdx = team.hitters.findIndex(s => s.player === null);
            if (emptyIdx === -1) return -999;
            team.hitters[emptyIdx].player = player;
            newWins = getExpectedWins('Skrey').wins.TOTAL;
            team.hitters[emptyIdx].player = null;"""

    new_marginal = """function calculateMarginalValue(player) {
        const team = allTeams['Skrey'];
        const currentWins = getExpectedWins('Skrey').wins.TOTAL;
        let newWins;

        if (player.type === 'H') {
            // In-season: evaluate hitter for C slot (index 0) specifically
            const cSlot = team.hitters[0]; // C is always index 0
            if (cSlot.player !== null) return -999; // C slot already filled
            cSlot.player = { ...player, type: 'H' };
            newWins = getExpectedWins('Skrey').wins.TOTAL;
            cSlot.player = null;"""

    content = content.replace(old_marginal, new_marginal)

    return content


def main():
    print("Loading draft_tool.html...")
    with open(HTML_FILE, 'r') as f:
        content = f.read()

    print("Building projection name lookup...")
    all_proj_names = build_proj_name_lookup(content)
    print(f"  Found {len(all_proj_names)} projection names")

    print("\nBuilding rosters from Post-Draft_Rosters.csv...")
    rosters_data = build_rosters_from_csv(all_proj_names)
    total_players = sum(len(v) for v in rosters_data.values())
    print(f"  {len(rosters_data)} teams, {total_players} total players")
    for team in sorted(rosters_data):
        names = [k['name'] for k in rosters_data[team]]
        print(f"  {team} ({len(names)}): {names}")

    print("\n--- Creating Team Rankings ---")
    team_rankings = create_team_rankings(content, rosters_data)
    with open(TEAM_RANKINGS_OUT, 'w') as f:
        f.write(team_rankings)
    print(f"  Written to {TEAM_RANKINGS_OUT}")

    print("\n--- Creating In Season Rankings ---")
    in_season = create_in_season_rankings(content, rosters_data)
    with open(IN_SEASON_OUT, 'w') as f:
        f.write(in_season)
    print(f"  Written to {IN_SEASON_OUT}")

    print("\nDone!")


if __name__ == '__main__':
    main()
