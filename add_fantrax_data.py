#!/usr/bin/env python3
"""
Patches draft_tool.html with Fantrax data:
1. Adds positional eligibility ('pos' field) to all hitter/pitcher data arrays
2. Embeds a KEEPERS object keyed by Fantrax team name
3. Updates TEAM_NAMES to use Fantrax team names
"""

import csv
import json
import re
import unicodedata

FANTRAX_FILE = "/home/user/FBB/Fantrax-Players-Kevin's League.csv"
HTML_FILE = "/home/user/FBB/draft_tool.html"

# Team name mapping: Fantrax name -> old HTML name
# "My Team" (Skrey) stays as the user's team
FANTRAX_TEAMS = [
    'Skrey', 'JDM', 'BigJoe', 'Ferrante', 'Rut', 'Gwon',
    'Beefs', 'Unks', 'Swagga', 'Triz', 'Boofers', 'BShit',
    'DertyDer', 'wes11', 'DGreasy', 'Diarrhea'
]

MY_TEAM = 'Skrey'


def normalize(name):
    """Strip accents, punctuation, and normalize whitespace for name matching."""
    nfkd = unicodedata.normalize('NFKD', name)
    n = ''.join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()
    n = n.replace("'", "").replace("\u2019", "").replace("-", " ").replace(".", "").replace(",", "")
    return ' '.join(n.split())


def load_fantrax():
    """Load Fantrax CSV into a normalized-name lookup.

    For duplicate names (e.g. 3 different "Jose Ramirez"), keeps the
    highest-ranked entry (lowest RkOv) since that's the MLB player.
    """
    fantrax = {}
    fantrax_rank = {}  # track best rank per normalized name
    with open(FANTRAX_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            n = normalize(row['Player'])
            try:
                rank = int(row['RkOv'])
            except (ValueError, KeyError):
                rank = 99999
            # Keep the highest-ranked (lowest number) entry for each name
            if n not in fantrax or rank < fantrax_rank.get(n, 99999):
                fantrax[n] = {
                    'original_name': row['Player'],
                    'position': row['Position'],
                    'status': row['Status']
                }
                fantrax_rank[n] = rank
    # Special case: "Shohei Ohtani" in projections is the hitter ("Shohei Ohtani-H" in Fantrax)
    ohtani_h = fantrax.get(normalize('Shohei Ohtani-H'))
    if ohtani_h:
        fantrax[normalize('Shohei Ohtani')] = ohtani_h
    return fantrax


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


def add_positions_to_hitters(content, fantrax):
    """Add 'pos' field to all three hitter arrays."""
    for prefix in ['HITTERS_THEBAT = [', 'HITTERS_BATX = [', 'HITTERS_DC = [']:
        arr, start, end = extract_json_array(content, prefix)
        matched = 0
        for h in arr:
            n = normalize(h['name'])
            if n in fantrax:
                h['pos'] = fantrax[n]['position'].split(',')
                matched += 1
            else:
                h['pos'] = []
        print(f"  {prefix.split('=')[0].strip()}: matched {matched}/{len(arr)}")
        new_json = json.dumps(arr, separators=(',', ':'))
        content = content[:start] + new_json + content[end:]
    return content


def add_positions_to_pitchers(content, fantrax):
    """Add 'pos' field to pitchers with dual SP/RP eligibility."""
    arr, start, end = extract_json_array(content, 'const PITCHERS = [')
    matched = 0
    for p in arr:
        n = normalize(p['name'])
        if n in fantrax:
            pos = fantrax[n]['position']
            positions = pos.split(',')
            is_sp = 'SP' in positions
            is_rp = 'RP' in positions
            if is_sp and is_rp:
                p['dualEligible'] = True
            matched += 1
    print(f"  PITCHERS: matched {matched}/{len(arr)}")
    new_json = json.dumps(arr, separators=(',', ':'))
    content = content[:start] + new_json + content[end:]
    return content


def build_keepers(fantrax, all_proj_names):
    """
    Build keepers dict: { teamName: [ {name, type, position?}, ... ] }
    Uses projection names (with accents) so they match the embedded data.
    """
    keepers = {}
    with open(FANTRAX_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['Status'] == 'FA':
                continue
            team = row['Status']
            if team not in keepers:
                keepers[team] = []

            fx_name = row['Player']
            pos = row['Position']
            positions = pos.split(',')
            has_batting = any(p in ('C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'UT') for p in positions)
            has_pitching = any(p in ('SP', 'RP') for p in positions)

            # Resolve to projection name
            n = normalize(fx_name)
            proj_name = all_proj_names.get(n)
            if not proj_name:
                # Special case Ohtani hitter
                if fx_name == 'Shohei Ohtani-H':
                    proj_name = all_proj_names.get(normalize('Shohei Ohtani'))
                if not proj_name:
                    print(f"  WARNING: Keeper '{fx_name}' ({team}) not found in projections, skipping")
                    continue

            if has_pitching and not has_batting:
                ptype = 'SP' if 'SP' in positions else 'RP'
                keepers[team].append({'name': proj_name, 'type': ptype})
            else:
                keepers[team].append({'name': proj_name, 'type': 'H', 'position': pos})

    return keepers


def update_team_names(content):
    """Replace TEAM_NAMES array with Fantrax team names."""
    old_pattern = r"const TEAM_NAMES = \[.*?\];"
    new_value = f"const TEAM_NAMES = {json.dumps(FANTRAX_TEAMS)};"
    content = re.sub(old_pattern, new_value, content)
    return content


def update_my_team_references(content):
    """Replace 'My Team' references with the Fantrax team name."""
    content = content.replace("'My Team'", f"'{MY_TEAM}'")
    content = content.replace('"My Team"', f'"{MY_TEAM}"')
    return content


def embed_keepers(content, keepers_data):
    """Replace the initKeepers() function with one that loads all teams' keepers."""
    keepers_json = json.dumps(keepers_data, ensure_ascii=False, separators=(',', ':'))

    new_init = f"""(function initKeepers() {{
        const KEEPERS = {keepers_json};

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
    }})();"""

    # Replace the old initKeepers block
    pattern = r'\(function initKeepers\(\) \{.*?\}\)\(\);'
    content = re.sub(pattern, new_init, content, flags=re.DOTALL)
    return content


def main():
    print("Loading Fantrax data...")
    fantrax = load_fantrax()
    print(f"  Loaded {len(fantrax)} Fantrax entries")

    print("\nReading draft_tool.html...")
    with open(HTML_FILE, 'r') as f:
        content = f.read()

    # Build projection name lookup from all hitter/pitcher arrays
    all_proj_names = {}
    for prefix in ['HITTERS_THEBAT = [', 'HITTERS_BATX = [', 'HITTERS_DC = [']:
        arr, _, _ = extract_json_array(content, prefix)
        for h in arr:
            all_proj_names[normalize(h['name'])] = h['name']
    arr, _, _ = extract_json_array(content, 'const PITCHERS = [')
    for p in arr:
        all_proj_names[normalize(p['name'])] = p['name']
    # Ohtani special case
    all_proj_names[normalize('Shohei Ohtani-H')] = all_proj_names.get(normalize('Shohei Ohtani'), 'Shohei Ohtani')

    print("\nAdding positional eligibility to hitters...")
    content = add_positions_to_hitters(content, fantrax)

    print("\nAdding dual eligibility to pitchers...")
    content = add_positions_to_pitchers(content, fantrax)

    print("\nBuilding keepers...")
    keepers_data = build_keepers(fantrax, all_proj_names)
    for team in sorted(keepers_data):
        names = [k['name'] for k in keepers_data[team]]
        print(f"  {team} ({len(names)}): {names}")

    print("\nUpdating team names...")
    content = update_team_names(content)
    content = update_my_team_references(content)

    print("\nEmbedding keepers initialization...")
    content = embed_keepers(content, keepers_data)

    print("\nWriting updated draft_tool.html...")
    with open(HTML_FILE, 'w') as f:
        f.write(content)
    print("Done!")


if __name__ == '__main__':
    main()
