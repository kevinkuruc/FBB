import csv

"""
Normalize The Bat playing time to match Depth Charts.

For each player in The Bat:
1. Find them in Depth Charts
2. Scale counting stats by (DC_PA / TheBat_PA)
3. Set PA to DC's PA
4. Keep rate stats (OBP, K%, etc.) unchanged

This isolates the projection differences to just rate/skill projections,
removing playing time disagreements between systems.
"""

# Input files
thebat_file = '/home/user/FBB/The_Bat_Raw_Jan_25.csv'
dc_file = '/home/user/FBB/DC_Raw_Jan_25.csv'
output_file = '/home/user/FBB/The_Bat_Normalized_PA.csv'

# Minimum PA filter - only include players with >= MIN_PA in Depth Charts
MIN_PA = 300

# Read Depth Charts to get PA by player name (only those meeting MIN_PA threshold)
dc_pa = {}
with open(dc_file, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        name = row['Name']
        try:
            pa = float(row['PA'])
            if pa >= MIN_PA:
                dc_pa[name] = pa
        except (ValueError, KeyError):
            continue

print(f"Loaded {len(dc_pa)} eligible players with >= {MIN_PA} PA from Depth Charts")

# Read The Bat and normalize PA
normalized_rows = []
matched = 0
unmatched = 0

with open(thebat_file, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames

    for row in reader:
        name = row['Name']

        try:
            thebat_pa = float(row['PA'])
        except (ValueError, KeyError):
            continue

        if name in dc_pa and thebat_pa > 0:
            # Calculate scaling factor
            target_pa = dc_pa[name]
            scale = target_pa / thebat_pa

            # Scale counting stats
            counting_stats = ['AB', 'H', '1B', '2B', '3B', 'HR', 'R', 'RBI', 'BB', 'IBB', 'SO', 'HBP', 'SF', 'SH', 'GDP', 'SB', 'CS']

            new_row = row.copy()
            new_row['PA'] = str(target_pa)

            for stat in counting_stats:
                if stat in row and row[stat]:
                    try:
                        original = float(row[stat])
                        new_row[stat] = str(original * scale)
                    except ValueError:
                        pass

            normalized_rows.append(new_row)
            matched += 1
        else:
            # Player not in DC eligible pool - skip them (don't include in output)
            unmatched += 1

print(f"Matched {matched} players, {unmatched} unmatched (kept original)")

# Write output
with open(output_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(normalized_rows)

print(f"Created {output_file}")

# Show some examples of the normalization
print("\nExample normalizations (first 10 matched players):")
print(f"{'Player':<25} {'TheBat PA':>10} {'DC PA':>10} {'Scale':>8}")
print("-" * 55)

with open(thebat_file, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    count = 0
    for row in reader:
        name = row['Name']
        if name in dc_pa:
            thebat_pa = float(row['PA'])
            target_pa = dc_pa[name]
            scale = target_pa / thebat_pa
            print(f"{name:<25} {thebat_pa:>10.1f} {target_pa:>10.1f} {scale:>8.3f}")
            count += 1
            if count >= 10:
                break
