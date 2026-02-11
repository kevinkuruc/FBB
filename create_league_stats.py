import csv
import sys

# Read the raw data and create a clean CSV with only relevant fantasy categories
# Can be overridden via command line: python create_league_stats.py <input_file> <output_file>
if len(sys.argv) >= 3:
    input_file = sys.argv[1]
    output_file = sys.argv[2]
else:
    input_file = '/home/user/FBB/The_Bat_Raw_Jan_25.csv'
    output_file = '/home/user/FBB/fantasy_hitters_2026.csv'

# Minimum PA filter - use Depth Charts PA projections as the source of truth
# Players with < MIN_PA in Depth Charts are excluded from the pool
MIN_PA = 300
DC_FILE = '/home/user/FBB/DC_Raw_Jan_25.csv'

# Build set of eligible players (those with >= MIN_PA in Depth Charts)
eligible_players = set()
with open(DC_FILE, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            if float(row['PA']) >= MIN_PA:
                eligible_players.add(row['Name'])
        except (ValueError, KeyError):
            pass
print(f"Loaded {len(eligible_players)} eligible players with >= {MIN_PA} PA from Depth Charts")

# Weekly standard deviations from 2024 league data
SD_R = 6.03
SD_HR = 2.93
SD_RBI = 6.72
SD_SB = 2.57
SD_SO = 7.45
SD_TB = 15.94
SD_OBP = 0.04

# League average OBP for baseline
AVG_OBP = 0.32

# Number of weeks in season
NUM_WEEKS = 25

# Target PA - all players supplemented to this level with replacement production
TARGET_PA = 600

# Replacement level per-PA rates
# Methodology: Using Depth Charts projections, players are ranked by zTotal.
# Replacement level is defined as the average production of players ranked 155-175.
# This represents the talent pool just beyond typical draft depth (16 teams x 9 hitters = 144).
# These rates are used to supplement low-PA players to a 600 PA baseline.
#
# Cohort (ranks 155-175, Jan 2026 DC projections):
# Spencer Steer, Miguel Andujar, Ezequiel Tovar, Jonathan Aranda, Addison Barger,
# Nathan Lukes, Kyle Manzardo, Colt Keith, Josh Lowe, Romy Gonzalez, Samuel Basallo,
# Francisco Alvarez, Lars Nootbaar, Joey Ortiz, Tyler O'Neill, Ryan O'Hearn,
# Victor Robles, Jake Fraley, JJ Bleday, Munetaka Murakami, Chase Meidroth
#
# Cohort totals (21 players): 10292 PA, 1247 R, 340 HR, 1243 RBI, 2291 SO, 3834 TB, 156 SB
# Average PA: 490.1, Average OBP: 0.324
REP_R_PER_PA = 0.121162    # 1247 R / 10292 PA
REP_HR_PER_PA = 0.033035   # 340 HR / 10292 PA
REP_RBI_PER_PA = 0.120773  # 1243 RBI / 10292 PA
REP_SO_PER_PA = 0.222623   # 2291 SO / 10292 PA
REP_TB_PER_PA = 0.372522   # 3834 TB / 10292 PA
REP_SB_PER_PA = 0.015157   # 156 SB / 10292 PA
REP_OBP = 0.320            # Capped at league average (2024: 0.320) to ensure replacement is OBP-neutral

with open(input_file, 'r', encoding='utf-8-sig') as infile:
    reader = csv.DictReader(infile)

    # Prepare output data
    output_rows = []

    for row in reader:
        try:
            # Extract raw values
            name = row['Name']

            # Skip players not in eligible pool (< MIN_PA in Depth Charts)
            if name not in eligible_players:
                continue

            pa = float(row['PA'])
            k_pct = float(row['K%'])
            singles = float(row['1B'])
            doubles = float(row['2B'])
            triples = float(row['3B'])
            hr = float(row['HR'])
            runs = float(row['R'])
            rbi = float(row['RBI'])
            sb = float(row['SB'])
            obp = float(row['OBP'])

            # Calculate Strikeouts: K% * PA
            strikeouts = k_pct * pa

            # Calculate Total Bases: 1B + 2*2B + 3*3B + 4*HR
            total_bases = singles + (2 * doubles) + (3 * triples) + (4 * hr)

            # Supplement low-PA players with replacement-level production
            if pa < TARGET_PA:
                gap_pa = TARGET_PA - pa
                runs = runs + gap_pa * REP_R_PER_PA
                hr = hr + gap_pa * REP_HR_PER_PA
                rbi = rbi + gap_pa * REP_RBI_PER_PA
                strikeouts = strikeouts + gap_pa * REP_SO_PER_PA
                total_bases = total_bases + gap_pa * REP_TB_PER_PA
                sb = sb + gap_pa * REP_SB_PER_PA
                # OBP is weighted average
                obp = (pa * obp + gap_pa * REP_OBP) / TARGET_PA
                pa = TARGET_PA

            # Calculate z-scores
            # Counting stats: (season_stat / NUM_WEEKS) / SD
            z_r = (runs / NUM_WEEKS) / SD_R
            z_hr = (hr / NUM_WEEKS) / SD_HR
            z_rbi = (rbi / NUM_WEEKS) / SD_RBI
            z_sb = (sb / NUM_WEEKS) / SD_SB
            z_tb = (total_bases / NUM_WEEKS) / SD_TB

            # Strikeouts: negative because lower is better
            z_so = -(strikeouts / NUM_WEEKS) / SD_SO

            # OBP: (player_OBP - avg_OBP) / 9 / SD_OBP
            z_obp = (obp - AVG_OBP) / 9 / SD_OBP

            # Total z-score
            z_total = z_r + z_hr + z_rbi + z_sb + z_tb + z_so + z_obp

            output_rows.append({
                'Name': name,
                'PA': round(pa),
                'R': round(runs),
                'HR': round(hr),
                'RBI': round(rbi),
                'SO': round(strikeouts),
                'TB': round(total_bases),
                'SB': round(sb),
                'OBP': round(obp, 3),
                'zR': round(z_r, 2),
                'zHR': round(z_hr, 2),
                'zRBI': round(z_rbi, 2),
                'zSO': round(z_so, 2),
                'zTB': round(z_tb, 2),
                'zSB': round(z_sb, 2),
                'zOBP': round(z_obp, 2),
                'zTotal': round(z_total, 2)
            })
        except (ValueError, KeyError) as e:
            # Skip rows with missing/invalid data
            print(f"Skipping row due to error: {e}")
            continue

# Sort by total z-score descending (best players first)
output_rows.sort(key=lambda x: x['zTotal'], reverse=True)

# Write output CSV
fieldnames = ['Name', 'PA', 'R', 'HR', 'RBI', 'SO', 'TB', 'SB', 'OBP',
              'zR', 'zHR', 'zRBI', 'zSO', 'zTB', 'zSB', 'zOBP', 'zTotal']
with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(output_rows)

print(f"Created {output_file} with {len(output_rows)} players")
print("\nTop 15 players by total z-score:")
print(f"{'Name':<25} {'zR':>5} {'zHR':>5} {'zRBI':>5} {'zSO':>5} {'zTB':>5} {'zSB':>5} {'zOBP':>5} {'zTot':>6}")
print("-" * 80)
for row in output_rows[:15]:
    print(f"{row['Name']:<25} {row['zR']:>5} {row['zHR']:>5} {row['zRBI']:>5} {row['zSO']:>5} {row['zTB']:>5} {row['zSB']:>5} {row['zOBP']:>5} {row['zTotal']:>6}")
