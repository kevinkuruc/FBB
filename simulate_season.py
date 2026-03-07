#!/usr/bin/env python3
"""
Fantasy Baseball Season Simulator — Calibration Tool

Simulates a 16-team fantasy baseball season. Each weekly matchup draws a
"percentage of categories won" from a normal distribution centered on the
talent difference between two teams, clipped to [0, 1].

Quick-start:
    1. Edit TEAM_STRENGTHS below (win probabilities, 0.50 = average)
    2. Edit NOISE_MULTIPLIER (higher = more week-to-week chaos)
    3. Run:  python simulate_season.py
    4. Look at the density plot + calibration stats to see if it matches
       what your league actually looks like.

Usage:
    python simulate_season.py [--sims N] [--seed S] [--noise-mult M]
"""

import argparse
import math
import random
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ============================================================
# >>>  TINKER WITH THESE  <<<
# ============================================================

DIVISIONS = {
    "YGG": [
        "Skrey's Squad",
        "Beasts of the East",
        "Acuna Matata",
        "Put Up or Shut Up",
    ],
    "Summer Krew": [
        "wes11",
        "Polar Bears",
        "Derty's Rolling Crew",
        "Cleveland Steamers",
    ],
    "Benders": [
        "Tardy Plumbers",
        "North Shore Beefs",
        "vves11",
        "Unkle Jerik",
    ],
    "Breeders": [
        "$wagga",
        "Shmoulie",
        "The Bronx Boofers",
        "The Murk Master",
    ],
}

ALL_TEAMS = [team for teams in DIVISIONS.values() for team in teams]

TEAM_TO_DIVISION = {}
for _div, _teams in DIVISIONS.items():
    for _team in _teams:
        TEAM_TO_DIVISION[_team] = _div

# ------------------------------------------------------------------
# True-talent win probabilities.
# 0.50 = perfectly average.  0.55 = wins 55% of categories vs average.
# ------------------------------------------------------------------
TEAM_STRENGTHS = {
    # --- YGG ---
    "Skrey's Squad":        0.50,
    "Beasts of the East":   0.50,
    "Acuna Matata":         0.50,
    "Put Up or Shut Up":    0.50,
    # --- Summer Krew ---
    "wes11":                0.50,
    "Polar Bears":          0.50,
    "Derty's Rolling Crew": 0.50,
    "Cleveland Steamers":   0.50,
    # --- Benders ---
    "Tardy Plumbers":       0.50,
    "North Shore Beefs":    0.50,
    "vves11":               0.50,
    "Unkle Jerik":          0.50,
    # --- Breeders ---
    "$wagga":               0.50,
    "Shmoulie":             0.50,
    "The Bronx Boofers":    0.50,
    "The Murk Master":      0.50,
}

# ------------------------------------------------------------------
# Noise multiplier: weekly noise variance = NOISE_MULTIPLIER * talent variance.
#   Low  (2-3): season outcomes very predictable from talent
#   Mid  (5):   talent shows over a season, but any week is a coin flip
#   High (10+): even season standings have lots of randomness
# ------------------------------------------------------------------
NOISE_MULTIPLIER = 5.0

# Floor for weekly noise SD (used when all teams are equal or nearly equal)
MIN_NOISE_SD = 0.05

# ============================================================
# Other settings (less likely to change)
# ============================================================

NUM_CATEGORIES = 14
TIE_PROB = 0.03
PLAYOFF_HIGHER_SEED_WINS_TIE = True


# ============================================================
# SCHEDULE — 20 regular-season scoring periods
# ============================================================

SCHEDULE = [
    # --- Scoring Period 1 (Mar 25 – Apr 5) ---
    [
        ("$wagga", "The Bronx Boofers"),
        ("Acuna Matata", "Beasts of the East"),
        ("Cleveland Steamers", "Derty's Rolling Crew"),
        ("Polar Bears", "wes11"),
        ("Unkle Jerik", "Tardy Plumbers"),
        ("vves11", "North Shore Beefs"),
        ("Skrey's Squad", "Put Up or Shut Up"),
        ("Shmoulie", "The Murk Master"),
    ],
    # --- Scoring Period 2 (Apr 6 – Apr 12) ---
    [
        ("Acuna Matata", "Put Up or Shut Up"),
        ("Cleveland Steamers", "Polar Bears"),
        ("The Murk Master", "$wagga"),
        ("wes11", "Derty's Rolling Crew"),
        ("Tardy Plumbers", "North Shore Beefs"),
        ("Beasts of the East", "Skrey's Squad"),
        ("Unkle Jerik", "vves11"),
        ("Shmoulie", "The Bronx Boofers"),
    ],
    # --- Scoring Period 3 (Apr 13 – Apr 19) ---
    [
        ("$wagga", "Shmoulie"),
        ("Cleveland Steamers", "wes11"),
        ("The Murk Master", "The Bronx Boofers"),
        ("Polar Bears", "Derty's Rolling Crew"),
        ("Tardy Plumbers", "vves11"),
        ("Beasts of the East", "Put Up or Shut Up"),
        ("Skrey's Squad", "Acuna Matata"),
        ("North Shore Beefs", "Unkle Jerik"),
    ],
    # --- Scoring Period 4 (Apr 20 – Apr 26) ---
    [
        ("Cleveland Steamers", "$wagga"),
        ("The Murk Master", "Derty's Rolling Crew"),
        ("Polar Bears", "The Bronx Boofers"),
        ("Put Up or Shut Up", "North Shore Beefs"),
        ("Tardy Plumbers", "Beasts of the East"),
        ("vves11", "Acuna Matata"),
        ("Skrey's Squad", "Unkle Jerik"),
        ("Shmoulie", "wes11"),
    ],
    # --- Scoring Period 5 (Apr 27 – May 3) ---
    [
        ("$wagga", "Polar Bears"),
        ("Acuna Matata", "Unkle Jerik"),
        ("The Murk Master", "wes11"),
        ("The Bronx Boofers", "Derty's Rolling Crew"),
        ("Put Up or Shut Up", "Tardy Plumbers"),
        ("Beasts of the East", "vves11"),
        ("Skrey's Squad", "North Shore Beefs"),
        ("Shmoulie", "Cleveland Steamers"),
    ],
    # --- Scoring Period 6 (May 4 – May 10) ---
    [
        ("$wagga", "Derty's Rolling Crew"),
        ("Acuna Matata", "North Shore Beefs"),
        ("The Murk Master", "Cleveland Steamers"),
        ("The Bronx Boofers", "wes11"),
        ("Put Up or Shut Up", "vves11"),
        ("Beasts of the East", "Unkle Jerik"),
        ("Skrey's Squad", "Tardy Plumbers"),
        ("Shmoulie", "Polar Bears"),
    ],
    # --- Scoring Period 7 (May 11 – May 17) ---
    [
        ("$wagga", "wes11"),
        ("Acuna Matata", "Tardy Plumbers"),
        ("The Murk Master", "Polar Bears"),
        ("The Bronx Boofers", "Cleveland Steamers"),
        ("Put Up or Shut Up", "Unkle Jerik"),
        ("Beasts of the East", "North Shore Beefs"),
        ("Skrey's Squad", "vves11"),
        ("Shmoulie", "Derty's Rolling Crew"),
    ],
    # --- Scoring Period 8 (May 18 – May 24) ---
    [
        ("$wagga", "North Shore Beefs"),
        ("Acuna Matata", "Derty's Rolling Crew"),
        ("The Murk Master", "vves11"),
        ("The Bronx Boofers", "Tardy Plumbers"),
        ("Put Up or Shut Up", "Cleveland Steamers"),
        ("Beasts of the East", "Polar Bears"),
        ("Skrey's Squad", "wes11"),
        ("Shmoulie", "Unkle Jerik"),
    ],
    # --- Scoring Period 9 (May 25 – May 31) ---
    [
        ("$wagga", "Tardy Plumbers"),
        ("Acuna Matata", "wes11"),
        ("The Murk Master", "Unkle Jerik"),
        ("The Bronx Boofers", "vves11"),
        ("Put Up or Shut Up", "Polar Bears"),
        ("Beasts of the East", "Derty's Rolling Crew"),
        ("Skrey's Squad", "Cleveland Steamers"),
        ("Shmoulie", "North Shore Beefs"),
    ],
    # --- Scoring Period 10 (Jun 1 – Jun 7) ---
    [
        ("$wagga", "vves11"),
        ("Acuna Matata", "Cleveland Steamers"),
        ("The Murk Master", "North Shore Beefs"),
        ("The Bronx Boofers", "Unkle Jerik"),
        ("Put Up or Shut Up", "Derty's Rolling Crew"),
        ("Beasts of the East", "wes11"),
        ("Skrey's Squad", "Polar Bears"),
        ("Shmoulie", "Tardy Plumbers"),
    ],
    # --- Scoring Period 11 (Jun 8 – Jun 14) ---
    [
        ("$wagga", "Unkle Jerik"),
        ("Acuna Matata", "Polar Bears"),
        ("The Murk Master", "Tardy Plumbers"),
        ("The Bronx Boofers", "North Shore Beefs"),
        ("Put Up or Shut Up", "wes11"),
        ("Beasts of the East", "Cleveland Steamers"),
        ("Skrey's Squad", "Derty's Rolling Crew"),
        ("Shmoulie", "vves11"),
    ],
    # --- Scoring Period 12 (Jun 15 – Jun 21) ---
    [
        ("Acuna Matata", "The Murk Master"),
        ("Cleveland Steamers", "Unkle Jerik"),
        ("Derty's Rolling Crew", "Tardy Plumbers"),
        ("wes11", "vves11"),
        ("Polar Bears", "North Shore Beefs"),
        ("Put Up or Shut Up", "$wagga"),
        ("Beasts of the East", "The Bronx Boofers"),
        ("Skrey's Squad", "Shmoulie"),
    ],
    # --- Scoring Period 13 (Jun 22 – Jun 28) ---
    [
        ("Acuna Matata", "Shmoulie"),
        ("Cleveland Steamers", "North Shore Beefs"),
        ("Derty's Rolling Crew", "vves11"),
        ("wes11", "Unkle Jerik"),
        ("Polar Bears", "Tardy Plumbers"),
        ("Put Up or Shut Up", "The Bronx Boofers"),
        ("Beasts of the East", "The Murk Master"),
        ("Skrey's Squad", "$wagga"),
    ],
    # --- Scoring Period 14 (Jun 29 – Jul 5) ---
    [
        ("Acuna Matata", "$wagga"),
        ("Cleveland Steamers", "Tardy Plumbers"),
        ("Derty's Rolling Crew", "Unkle Jerik"),
        ("wes11", "North Shore Beefs"),
        ("Polar Bears", "vves11"),
        ("Put Up or Shut Up", "The Murk Master"),
        ("Beasts of the East", "Shmoulie"),
        ("Skrey's Squad", "The Bronx Boofers"),
    ],
    # --- Scoring Period 15 (Jul 6 – Jul 12) ---
    [
        ("Acuna Matata", "The Bronx Boofers"),
        ("Cleveland Steamers", "vves11"),
        ("Derty's Rolling Crew", "North Shore Beefs"),
        ("wes11", "Tardy Plumbers"),
        ("Polar Bears", "Unkle Jerik"),
        ("Put Up or Shut Up", "Shmoulie"),
        ("Beasts of the East", "$wagga"),
        ("Skrey's Squad", "The Murk Master"),
    ],
    # --- Scoring Period 16 (Jul 13 – Jul 26) ---
    [
        ("$wagga", "Cleveland Steamers"),
        ("Acuna Matata", "vves11"),
        ("The Murk Master", "Derty's Rolling Crew"),
        ("The Bronx Boofers", "Polar Bears"),
        ("Put Up or Shut Up", "North Shore Beefs"),
        ("Beasts of the East", "Tardy Plumbers"),
        ("Skrey's Squad", "Unkle Jerik"),
        ("Shmoulie", "wes11"),
    ],
    # --- Scoring Period 17 (Jul 27 – Aug 2) ---
    [
        ("$wagga", "North Shore Beefs"),
        ("Acuna Matata", "Derty's Rolling Crew"),
        ("The Murk Master", "vves11"),
        ("The Bronx Boofers", "Tardy Plumbers"),
        ("Put Up or Shut Up", "Cleveland Steamers"),
        ("Beasts of the East", "Polar Bears"),
        ("Skrey's Squad", "wes11"),
        ("Shmoulie", "Unkle Jerik"),
    ],
    # --- Scoring Period 18 (Aug 3 – Aug 9) ---
    [
        ("$wagga", "The Murk Master"),
        ("wes11", "Derty's Rolling Crew"),
        ("Polar Bears", "Cleveland Steamers"),
        ("Put Up or Shut Up", "Beasts of the East"),
        ("Unkle Jerik", "Tardy Plumbers"),
        ("vves11", "North Shore Beefs"),
        ("Skrey's Squad", "Acuna Matata"),
        ("Shmoulie", "The Bronx Boofers"),
    ],
    # --- Scoring Period 19 (Aug 10 – Aug 16) ---
    [
        ("$wagga", "Shmoulie"),
        ("Cleveland Steamers", "wes11"),
        ("The Murk Master", "The Bronx Boofers"),
        ("Polar Bears", "Derty's Rolling Crew"),
        ("Tardy Plumbers", "North Shore Beefs"),
        ("Beasts of the East", "Acuna Matata"),
        ("vves11", "Unkle Jerik"),
        ("Skrey's Squad", "Put Up or Shut Up"),
    ],
    # --- Scoring Period 20 (Aug 17 – Aug 23) ---
    [
        ("$wagga", "The Bronx Boofers"),
        ("Acuna Matata", "Put Up or Shut Up"),
        ("Cleveland Steamers", "Derty's Rolling Crew"),
        ("The Murk Master", "Shmoulie"),
        ("wes11", "Polar Bears"),
        ("Tardy Plumbers", "vves11"),
        ("Beasts of the East", "Skrey's Squad"),
        ("Unkle Jerik", "North Shore Beefs"),
    ],
]


# ============================================================
# VALIDATION
# ============================================================

def validate_schedule(schedule, all_teams):
    """Verify every week has 8 matchups covering all 16 teams exactly once."""
    for i, week in enumerate(schedule):
        teams_this_week = []
        for away, home in week:
            if away not in all_teams:
                raise ValueError(f"Week {i+1}: Unknown away team '{away}'")
            if home not in all_teams:
                raise ValueError(f"Week {i+1}: Unknown home team '{home}'")
            teams_this_week.extend([away, home])
        if len(teams_this_week) != len(all_teams):
            raise ValueError(
                f"Week {i+1}: Expected {len(all_teams)} teams, got {len(teams_this_week)}"
            )
        if set(teams_this_week) != set(all_teams):
            missing = set(all_teams) - set(teams_this_week)
            raise ValueError(f"Week {i+1}: Missing teams: {missing}")


# ============================================================
# SIMULATION FUNCTIONS
# ============================================================

def compute_noise_sd(strengths, noise_multiplier):
    """
    Compute weekly noise SD from the cross-team talent spread.
    noise_variance = noise_multiplier * talent_variance
    """
    vals = list(strengths.values())
    mean = sum(vals) / len(vals)
    talent_var = sum((v - mean) ** 2 for v in vals) / len(vals)
    noise_sd = math.sqrt(noise_multiplier * talent_var)
    return max(noise_sd, MIN_NOISE_SD)


def simulate_matchup(team_a, team_b, strengths, noise_sd):
    """
    Simulate one week's matchup.

    expected_pct_A = 0.5 + (talent_A - talent_B)
    actual_pct     = expected + Normal(0, noise_sd), clipped [0, 1]
    """
    expected_pct = 0.5 + (strengths[team_a] - strengths[team_b])
    expected_pct = max(0.0, min(1.0, expected_pct))

    actual_pct = expected_pct + random.gauss(0, noise_sd)
    actual_pct = max(0.0, min(1.0, actual_pct))

    # Ties per-category, then split remainder by drawn win%
    ties = sum(1 for _ in range(NUM_CATEGORIES) if random.random() < TIE_PROB)
    non_tie = NUM_CATEGORIES - ties

    exact_wins_a = actual_pct * non_tie
    floor_wins = int(exact_wins_a)
    frac = exact_wins_a - floor_wins
    wins_a = floor_wins + (1 if random.random() < frac else 0)
    wins_b = non_tie - wins_a

    return wins_a, wins_b, ties


def simulate_regular_season(schedule, strengths, noise_sd):
    """Simulate the full 20-week regular season. Returns per-team records."""
    records = {team: {"wins": 0, "losses": 0, "ties": 0} for team in ALL_TEAMS}
    for week in schedule:
        for away, home in week:
            w_away, w_home, t = simulate_matchup(away, home, strengths, noise_sd)
            records[away]["wins"] += w_away
            records[away]["losses"] += w_home
            records[away]["ties"] += t
            records[home]["wins"] += w_home
            records[home]["losses"] += w_away
            records[home]["ties"] += t
    return records


def determine_playoff_seeds(records):
    """Seeds 1-4: division winners ranked by record. Seeds 5-6: wild cards."""
    tiebreakers = {team: random.random() for team in ALL_TEAMS}

    def sort_key(team):
        r = records[team]
        return (r["wins"], -r["losses"], tiebreakers[team])

    div_winners = {}
    for div_name, teams in DIVISIONS.items():
        div_winners[div_name] = max(teams, key=sort_key)

    div_winner_list = sorted(div_winners.values(), key=sort_key, reverse=True)
    non_winners = sorted(
        [t for t in ALL_TEAMS if t not in div_winner_list],
        key=sort_key, reverse=True,
    )
    seeds = div_winner_list + non_winners[:2]
    return seeds, div_winners


def simulate_playoff_matchup(higher_seed, lower_seed, strengths, noise_sd):
    """One playoff week. Higher seed wins ties (configurable)."""
    w_h, w_l, t = simulate_matchup(higher_seed, lower_seed, strengths, noise_sd)
    if w_h > w_l:
        return higher_seed
    elif w_l > w_h:
        return lower_seed
    else:
        return higher_seed if PLAYOFF_HIGHER_SEED_WINS_TIE else random.choice([higher_seed, lower_seed])


def simulate_playoffs(seeds, strengths, noise_sd):
    """3-round bracket with reseeding. Returns champion."""
    r1_a = simulate_playoff_matchup(seeds[2], seeds[5], strengths, noise_sd)
    r1_b = simulate_playoff_matchup(seeds[3], seeds[4], strengths, noise_sd)

    remaining = sorted([
        (0, seeds[0]), (1, seeds[1]),
        (seeds.index(r1_a), r1_a), (seeds.index(r1_b), r1_b),
    ], key=lambda x: x[0])

    r2_a = simulate_playoff_matchup(remaining[0][1], remaining[3][1], strengths, noise_sd)
    r2_b = simulate_playoff_matchup(remaining[1][1], remaining[2][1], strengths, noise_sd)

    idx_a, idx_b = seeds.index(r2_a), seeds.index(r2_b)
    if idx_a < idx_b:
        return simulate_playoff_matchup(r2_a, r2_b, strengths, noise_sd)
    else:
        return simulate_playoff_matchup(r2_b, r2_a, strengths, noise_sd)


# ============================================================
# MONTE CARLO
# ============================================================

def run_simulations(n_sims, schedule, strengths, noise_multiplier, seed=None):
    """Run n_sims full seasons. Returns (stats dict, list of all season win-pcts)."""
    if seed is not None:
        random.seed(seed)

    validate_schedule(schedule, ALL_TEAMS)
    noise_sd = compute_noise_sd(strengths, noise_multiplier)

    # Print calibration header
    talent_vals = list(strengths.values())
    talent_mean = sum(talent_vals) / len(talent_vals)
    talent_sd = math.sqrt(sum((v - talent_mean) ** 2 for v in talent_vals) / len(talent_vals))
    if talent_sd > 0:
        ratio = noise_sd ** 2 / talent_sd ** 2
        print(f"  Talent SD: {talent_sd:.4f}  |  Weekly noise SD: {noise_sd:.4f}"
              f"  |  Noise/talent variance ratio: {ratio:.1f}x")
    else:
        print(f"  Talent SD: 0 (equal teams)  |  Weekly noise SD: {noise_sd:.4f}")

    stats = {team: {
        "total_wins": 0, "total_losses": 0, "total_ties": 0,
        "playoff_apps": 0, "div_titles": 0, "championships": 0,
        "seed_counts": defaultdict(int),
    } for team in ALL_TEAMS}

    # Collect every team's season win% for the density plot
    all_season_wpcts = []

    for _ in range(n_sims):
        records = simulate_regular_season(schedule, strengths, noise_sd)
        seeds, div_winners = determine_playoff_seeds(records)
        champion = simulate_playoffs(seeds, strengths, noise_sd)

        for team in ALL_TEAMS:
            r = records[team]
            stats[team]["total_wins"] += r["wins"]
            stats[team]["total_losses"] += r["losses"]
            stats[team]["total_ties"] += r["ties"]

            total = r["wins"] + r["losses"] + r["ties"]
            wpct = r["wins"] / total if total > 0 else 0.5
            all_season_wpcts.append(wpct)

        for i, team in enumerate(seeds):
            stats[team]["playoff_apps"] += 1
            stats[team]["seed_counts"][i + 1] += 1
        for winner in div_winners.values():
            stats[winner]["div_titles"] += 1
        stats[champion]["championships"] += 1

    return stats, all_season_wpcts


# ============================================================
# OUTPUT
# ============================================================

def print_results(stats, n_sims, all_season_wpcts):
    """Print tables + calibration stats, save density plot."""
    n_teams = len(ALL_TEAMS)

    # ---- Main standings table ----
    print(f"\n{'=' * 82}")
    print(f"  SEASON SIMULATION RESULTS  ({n_sims:,} simulations)")
    print(f"{'=' * 82}")

    sorted_teams = sorted(
        ALL_TEAMS,
        key=lambda t: (stats[t]["championships"], stats[t]["playoff_apps"], stats[t]["total_wins"]),
        reverse=True,
    )

    print(f"\n{'Team':<24} {'Avg Record':<16} {'Win%':>5}"
          f" {'Div%':>6} {'Playoff%':>9} {'Champ%':>7}")
    print(f"{'-' * 24} {'-' * 16} {'-' * 5}"
          f" {'-' * 6} {'-' * 9} {'-' * 7}")

    for team in sorted_teams:
        s = stats[team]
        avg_w = s["total_wins"] / n_sims
        avg_l = s["total_losses"] / n_sims
        avg_t = s["total_ties"] / n_sims
        total = avg_w + avg_l + avg_t
        win_pct = avg_w / total if total > 0 else 0
        record_str = f"{avg_w:.1f}-{avg_l:.1f}-{avg_t:.1f}"
        print(f"{team:<24} {record_str:<16} {win_pct:.3f}"
              f" {100*s['div_titles']/n_sims:>5.1f}%"
              f" {100*s['playoff_apps']/n_sims:>8.1f}%"
              f" {100*s['championships']/n_sims:>6.1f}%")

    # ---- Division breakdown ----
    print(f"\n{'=' * 82}")
    print(f"  DIVISION BREAKDOWN")
    print(f"{'=' * 82}")
    for div_name, teams in DIVISIONS.items():
        print(f"\n  {div_name}")
        print(f"  {'Team':<24} {'Div%':>6} {'Playoff%':>9} {'Champ%':>7}")
        print(f"  {'-' * 24} {'-' * 6} {'-' * 9} {'-' * 7}")
        for team in sorted(teams, key=lambda t: stats[t]["championships"], reverse=True):
            s = stats[team]
            print(f"  {team:<24}"
                  f" {100*s['div_titles']/n_sims:>5.1f}%"
                  f" {100*s['playoff_apps']/n_sims:>8.1f}%"
                  f" {100*s['championships']/n_sims:>6.1f}%")

    # ---- Seed distribution ----
    print(f"\n{'=' * 82}")
    print(f"  SEED DISTRIBUTION (% of simulations)")
    print(f"{'=' * 82}")
    print(f"\n{'Team':<24}", end="")
    for s in range(1, 7):
        print(f" {'Seed ' + str(s):>7}", end="")
    print()
    print(f"{'-' * 24}", end="")
    for _ in range(6):
        print(f" {'-' * 7}", end="")
    print()
    for team in sorted_teams:
        s = stats[team]
        if s["playoff_apps"] == 0:
            continue
        print(f"{team:<24}", end="")
        for seed_num in range(1, 7):
            pct = 100 * s["seed_counts"][seed_num] / n_sims
            print(f" {pct:>6.1f}%", end="")
        print()

    # ---- Calibration stats ----
    print(f"\n{'=' * 82}")
    print(f"  CALIBRATION STATS  (across all {n_sims:,} simulated seasons)")
    print(f"{'=' * 82}")

    above_600 = sum(1 for w in all_season_wpcts if w > 0.600)
    below_400 = sum(1 for w in all_season_wpcts if w < 0.400)
    above_550 = sum(1 for w in all_season_wpcts if w > 0.550)
    below_450 = sum(1 for w in all_season_wpcts if w < 0.450)
    above_650 = sum(1 for w in all_season_wpcts if w > 0.650)
    below_350 = sum(1 for w in all_season_wpcts if w < 0.350)

    total_team_seasons = len(all_season_wpcts)
    avg_wpcts = sorted(all_season_wpcts)
    median_wpct = avg_wpcts[len(avg_wpcts) // 2]
    sd_wpct = math.sqrt(sum((w - 0.5) ** 2 for w in all_season_wpcts) / total_team_seasons)

    best_pct = max(all_season_wpcts)
    worst_pct = min(all_season_wpcts)

    # Per-season expected counts (divide by n_sims since each season has 16 teams)
    print(f"\n  {'Metric':<45} {'Per season':>12}")
    print(f"  {'-' * 45} {'-' * 12}")
    print(f"  {'Teams above .650 win%':<45} {above_650/n_sims:>11.2f}")
    print(f"  {'Teams above .600 win%':<45} {above_600/n_sims:>11.2f}")
    print(f"  {'Teams above .550 win%':<45} {above_550/n_sims:>11.2f}")
    print(f"  {'Teams below .450 win%':<45} {below_450/n_sims:>11.2f}")
    print(f"  {'Teams below .400 win%':<45} {below_400/n_sims:>11.2f}")
    print(f"  {'Teams below .350 win%':<45} {below_350/n_sims:>11.2f}")
    print(f"\n  {'SD of season win%':<45} {sd_wpct:>11.4f}")
    print(f"  {'Median season win%':<45} {median_wpct:>11.4f}")
    print(f"  {'Best season win% seen':<45} {best_pct:>11.4f}")
    print(f"  {'Worst season win% seen':<45} {worst_pct:>11.4f}")

    # ---- Density plot ----
    plot_path = "season_winpct_density.png"
    fig, ax = plt.subplots(figsize=(10, 5))
    # 280 category decisions per season (20 wks × 14 cats) → win% in steps of 1/280.
    # 70 bins → width 1/140 = 2/280 → each bin catches exactly 2 discrete values.
    ax.hist(all_season_wpcts, bins=70, density=True, alpha=0.7,
            color="steelblue", edgecolor="white", linewidth=0.3)
    ax.axvline(0.600, color="green", linestyle="--", linewidth=1.5, label=".600")
    ax.axvline(0.400, color="red", linestyle="--", linewidth=1.5, label=".400")
    ax.axvline(0.500, color="gray", linestyle=":", linewidth=1)
    ax.set_xlabel("Season Win %", fontsize=12)
    ax.set_ylabel("Density", fontsize=12)
    ax.set_title(
        f"Distribution of Season Win% "
        f"({n_sims:,} sims × {n_teams} teams, noise mult = {NOISE_MULTIPLIER})",
        fontsize=13,
    )
    ax.legend(fontsize=10)
    ax.set_xlim(0.25, 0.75)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"\n  Density plot saved to: {plot_path}")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Fantasy Baseball Season Simulator — Calibration Tool",
    )
    parser.add_argument("--sims", type=int, default=10000,
                        help="Number of simulations (default: 10000)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducibility")
    parser.add_argument("--noise-mult", type=float, default=None,
                        help=f"Override NOISE_MULTIPLIER (default: {NOISE_MULTIPLIER})")
    args = parser.parse_args()

    noise_mult = args.noise_mult if args.noise_mult is not None else NOISE_MULTIPLIER

    print(f"Running {args.sims:,} season simulations...")
    if args.seed is not None:
        print(f"Random seed: {args.seed}")
    print(f"Noise multiplier: {noise_mult}")

    stats, all_wpcts = run_simulations(
        args.sims, SCHEDULE, TEAM_STRENGTHS, noise_mult, seed=args.seed,
    )
    print_results(stats, args.sims, all_wpcts)


if __name__ == "__main__":
    main()
