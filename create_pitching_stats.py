import csv

# Read the pitching data and create a clean CSV for fantasy purposes
input_file = '/home/user/FBB/ATC_Jan_26_Pitching.csv'
output_file = '/home/user/FBB/fantasy_pitchers_2026.csv'

# Weekly standard deviations from 2024 league data
SD_L = 1.8346
SD_SV = 1.5362
SD_K = 11.7861
SD_HLD = 1.6383
SD_ERA = 1.3141
SD_WHIP = 0.2057
SD_QS = 1.4012

# Number of weeks in season
NUM_WEEKS = 25

# SP model: 7 starts per week total, each SP contributes 1.1 starts/week
STARTS_PER_WEEK = 7
SP_CONTRIBUTION = 1.1  # starts per week per SP drafted

# RP model: 4 slots per day, each RP takes 1 slot
RP_SLOTS = 4

# Minimum WAR to include
MIN_WAR = 0.2

# SP Replacement per-start rates (from Brayan Bello, Cade Povich, Parker Messick, Shane Smith)
REP_SP_IP_PER_GS = 5.756
REP_SP_L_PER_GS = 0.3379
REP_SP_QS_PER_GS = 0.3797
REP_SP_K_PER_GS = 5.187
REP_SP_ER_PER_GS = 2.688
REP_SP_H_PER_GS = 5.449
REP_SP_BB_PER_GS = 1.998

# RP Replacement per-week rates (from Hunter Gaddis, A.J. Minter, Gabe Speier, Garrett Whitlock)
# These are per-RP rates (season stats / 25 weeks)
REP_RP_IP_PER_WK = 2.480
REP_RP_L_PER_WK = 0.1180
REP_RP_SV_PER_WK = 0.1208
REP_RP_HLD_PER_WK = 0.8484
REP_RP_K_PER_WK = 2.693
REP_RP_ER_PER_WK = 0.963
REP_RP_WH_PER_WK = 2.852  # Walks + Hits

# League average ERA and WHIP for baseline (from weekly data)
AVG_ERA = 3.7929
AVG_WHIP = 1.2048

with open(input_file, 'r', encoding='utf-8-sig') as infile:
    reader = csv.DictReader(infile)

    sp_rows = []
    rp_rows = []

    for row in reader:
        try:
            name = row['Name'].strip('"')
            war = float(row['WAR'])

            # Skip low-WAR players
            if war < MIN_WAR:
                continue

            gs = float(row['GS'])
            g = float(row['G'])
            ip = float(row['IP'])
            l = float(row['L'])
            sv = float(row['SV'])
            hld = float(row['HLD'])
            qs = float(row['QS'])
            k = float(row['SO'])
            er = float(row['ER'])
            h = float(row['H'])
            bb = float(row['BB'])
            era = float(row['ERA'])
            whip = float(row['WHIP'])

            # Classify as SP or RP based on GS ratio
            # SP if they have meaningful starts (GS > 5)
            is_sp = gs > 5

            if is_sp:
                # SP: compute per-start stats
                # Weekly contribution = 1.1 starts/week * per-start stats
                ip_per_gs = ip / gs
                l_per_gs = l / gs
                qs_per_gs = qs / gs
                k_per_gs = k / gs
                er_per_gs = er / gs
                wh_per_gs = (bb + h) / gs  # walks + hits for WHIP calc

                # Weekly stats (1.1 starts)
                ip_wk = ip_per_gs * SP_CONTRIBUTION
                l_wk = l_per_gs * SP_CONTRIBUTION
                qs_wk = qs_per_gs * SP_CONTRIBUTION
                k_wk = k_per_gs * SP_CONTRIBUTION
                er_wk = er_per_gs * SP_CONTRIBUTION
                wh_wk = wh_per_gs * SP_CONTRIBUTION

                # ERA and WHIP for the player's contribution
                # These are rate stats, so we use their projected rates
                player_era = era
                player_whip = whip

                sp_rows.append({
                    'Name': name,
                    'Type': 'SP',
                    'GS': round(gs, 1),
                    'IP': round(ip, 1),
                    'IP_wk': round(ip_wk, 2),
                    'L_wk': round(l_wk, 3),
                    'SV_wk': 0,  # SPs don't get saves
                    'HLD_wk': 0,  # SPs don't get holds
                    'K_wk': round(k_wk, 2),
                    'QS_wk': round(qs_wk, 3),
                    'ER_wk': round(er_wk, 3),
                    'WH_wk': round(wh_wk, 3),
                    'ERA': round(player_era, 3),
                    'WHIP': round(player_whip, 3),
                    'WAR': round(war, 2)
                })
            else:
                # RP: compute weekly stats (season / 25)
                ip_wk = ip / NUM_WEEKS
                l_wk = l / NUM_WEEKS
                sv_wk = sv / NUM_WEEKS
                hld_wk = hld / NUM_WEEKS
                k_wk = k / NUM_WEEKS
                er_wk = er / NUM_WEEKS
                wh_wk = (bb + h) / NUM_WEEKS

                rp_rows.append({
                    'Name': name,
                    'Type': 'RP',
                    'G': round(g, 1),
                    'IP': round(ip, 1),
                    'IP_wk': round(ip_wk, 2),
                    'L_wk': round(l_wk, 3),
                    'SV_wk': round(sv_wk, 3),
                    'HLD_wk': round(hld_wk, 3),
                    'K_wk': round(k_wk, 2),
                    'QS_wk': 0,  # RPs don't get QS
                    'ER_wk': round(er_wk, 3),
                    'WH_wk': round(wh_wk, 3),
                    'ERA': round(era, 3),
                    'WHIP': round(whip, 3),
                    'WAR': round(war, 2)
                })

        except (ValueError, KeyError) as e:
            continue

# Combine and sort by WAR descending
all_pitchers = sp_rows + rp_rows
all_pitchers.sort(key=lambda x: x['WAR'], reverse=True)

# Write output CSV
fieldnames = ['Name', 'Type', 'GS', 'G', 'IP', 'IP_wk', 'L_wk', 'SV_wk', 'HLD_wk', 'K_wk', 'QS_wk', 'ER_wk', 'WH_wk', 'ERA', 'WHIP', 'WAR']
with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
    writer = csv.DictWriter(outfile, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    for row in all_pitchers:
        # Fill in missing G/GS columns
        if 'G' not in row:
            row['G'] = ''
        if 'GS' not in row:
            row['GS'] = ''
        writer.writerow(row)

print(f"Created {output_file}")
print(f"  SPs: {len(sp_rows)} (WAR >= {MIN_WAR})")
print(f"  RPs: {len(rp_rows)} (WAR >= {MIN_WAR})")
print(f"  Total: {len(all_pitchers)}")

print("\nTop 15 SPs by WAR:")
print(f"{'Name':<25} {'GS':>5} {'IP_wk':>6} {'L_wk':>5} {'K_wk':>5} {'QS_wk':>5} {'ERA':>5} {'WHIP':>5}")
print("-" * 70)
for row in sorted(sp_rows, key=lambda x: x['WAR'], reverse=True)[:15]:
    print(f"{row['Name']:<25} {row['GS']:>5} {row['IP_wk']:>6} {row['L_wk']:>5} {row['K_wk']:>5} {row['QS_wk']:>5} {row['ERA']:>5} {row['WHIP']:>5}")

print("\nTop 15 RPs by WAR:")
print(f"{'Name':<25} {'G':>5} {'IP_wk':>6} {'SV_wk':>5} {'HLD_wk':>5} {'K_wk':>5} {'ERA':>5} {'WHIP':>5}")
print("-" * 70)
for row in sorted(rp_rows, key=lambda x: x['WAR'], reverse=True)[:15]:
    print(f"{row['Name']:<25} {row.get('G', 0):>5} {row['IP_wk']:>6} {row['SV_wk']:>5} {row['HLD_wk']:>5} {row['K_wk']:>5} {row['ERA']:>5} {row['WHIP']:>5}")

# Print replacement level weekly stats
print("\n" + "=" * 70)
print("REPLACEMENT LEVEL WEEKLY STATS:")
print("=" * 70)
print("\nSP Replacement (7 starts/week from replacement):")
sp_rep_ip = REP_SP_IP_PER_GS * STARTS_PER_WEEK
sp_rep_l = REP_SP_L_PER_GS * STARTS_PER_WEEK
sp_rep_k = REP_SP_K_PER_GS * STARTS_PER_WEEK
sp_rep_qs = REP_SP_QS_PER_GS * STARTS_PER_WEEK
sp_rep_er = REP_SP_ER_PER_GS * STARTS_PER_WEEK
sp_rep_wh = (REP_SP_H_PER_GS + REP_SP_BB_PER_GS) * STARTS_PER_WEEK
print(f"  IP/wk:  {sp_rep_ip:.2f}")
print(f"  L/wk:   {sp_rep_l:.3f}")
print(f"  K/wk:   {sp_rep_k:.2f}")
print(f"  QS/wk:  {sp_rep_qs:.3f}")
print(f"  ER/wk:  {sp_rep_er:.3f}")
print(f"  (W+H)/wk: {sp_rep_wh:.3f}")
print(f"  ERA:    {sp_rep_er * 9 / sp_rep_ip:.3f}")
print(f"  WHIP:   {sp_rep_wh / sp_rep_ip:.3f}")

print("\nRP Replacement (4 slots × replacement rate):")
rp_rep_ip = REP_RP_IP_PER_WK * RP_SLOTS
rp_rep_l = REP_RP_L_PER_WK * RP_SLOTS
rp_rep_sv = REP_RP_SV_PER_WK * RP_SLOTS
rp_rep_hld = REP_RP_HLD_PER_WK * RP_SLOTS
rp_rep_k = REP_RP_K_PER_WK * RP_SLOTS
rp_rep_er = REP_RP_ER_PER_WK * RP_SLOTS
rp_rep_wh = REP_RP_WH_PER_WK * RP_SLOTS
print(f"  IP/wk:  {rp_rep_ip:.2f}")
print(f"  L/wk:   {rp_rep_l:.3f}")
print(f"  SV/wk:  {rp_rep_sv:.3f}")
print(f"  HLD/wk: {rp_rep_hld:.3f}")
print(f"  K/wk:   {rp_rep_k:.2f}")
print(f"  ER/wk:  {rp_rep_er:.3f}")
print(f"  (W+H)/wk: {rp_rep_wh:.3f}")
print(f"  ERA:    {rp_rep_er * 9 / rp_rep_ip:.3f}")
print(f"  WHIP:   {rp_rep_wh / rp_rep_ip:.3f}")

print("\nTOTAL REPLACEMENT PITCHING (7 SP starts + 4 RP slots):")
total_ip = sp_rep_ip + rp_rep_ip
total_l = sp_rep_l + rp_rep_l
total_sv = rp_rep_sv  # Only RPs
total_hld = rp_rep_hld  # Only RPs
total_k = sp_rep_k + rp_rep_k
total_qs = sp_rep_qs  # Only SPs
total_er = sp_rep_er + rp_rep_er
total_wh = sp_rep_wh + rp_rep_wh
print(f"  IP/wk:  {total_ip:.2f}")
print(f"  L/wk:   {total_l:.3f}")
print(f"  SV/wk:  {total_sv:.3f}")
print(f"  HLD/wk: {total_hld:.3f}")
print(f"  K/wk:   {total_k:.2f}")
print(f"  QS/wk:  {total_qs:.3f}")
print(f"  ER/wk:  {total_er:.3f}")
print(f"  (W+H)/wk: {total_wh:.3f}")
print(f"  ERA:    {total_er * 9 / total_ip:.3f}")
print(f"  WHIP:   {total_wh / total_ip:.3f}")
