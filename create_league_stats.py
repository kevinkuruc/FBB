import csv

# Read the raw data and create a clean CSV with only relevant fantasy categories
input_file = '/home/user/FBB/The_Bat_Raw_Jan_25.csv'
output_file = '/home/user/FBB/fantasy_hitters_2026.csv'

with open(input_file, 'r', encoding='utf-8-sig') as infile:
    reader = csv.DictReader(infile)

    # Prepare output data
    output_rows = []

    for row in reader:
        try:
            # Extract raw values
            name = row['Name']
            pa = float(row['PA'])
            k_pct = float(row['K%'])  # This is already a decimal (e.g., 0.249456)
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

            output_rows.append({
                'Name': name,
                'PA': round(pa),
                'R': round(runs),
                'HR': round(hr),
                'RBI': round(rbi),
                'SO': round(strikeouts),
                'TB': round(total_bases),
                'SB': round(sb),
                'OBP': round(obp, 3)
            })
        except (ValueError, KeyError) as e:
            # Skip rows with missing/invalid data
            print(f"Skipping row due to error: {e}")
            continue

# Write output CSV
fieldnames = ['Name', 'PA', 'R', 'HR', 'RBI', 'SO', 'TB', 'SB', 'OBP']
with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(output_rows)

print(f"Created {output_file} with {len(output_rows)} players")
print("\nFirst 10 players:")
for row in output_rows[:10]:
    print(f"  {row['Name']}: PA={row['PA']}, R={row['R']}, HR={row['HR']}, RBI={row['RBI']}, SO={row['SO']}, TB={row['TB']}, SB={row['SB']}, OBP={row['OBP']}")
