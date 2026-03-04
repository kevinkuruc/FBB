#!/usr/bin/env python3
"""
Fantasy Baseball Season Simulator

Simulates a 16-team fantasy baseball season using the Bradley-Terry model
for category-by-category matchup outcomes. Supports division-based playoffs
with configurable team strengths.

Usage:
    python simulate_season.py [--sims N] [--seed S]
"""

import argparse
import random
from collections import defaultdict


# ============================================================
# LEAGUE CONFIGURATION
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

# Bradley-Terry strength parameters.
# The RATIO between two teams' strengths determines win probability.
# Default 1.0 = all teams equal.
# Example: 1.3 vs 1.0 means the stronger team wins each category ~56.5% of the time.
TEAM_STRENGTHS = {team: 1.0 for team in ALL_TEAMS}

NUM_CATEGORIES = 14  # 7 hitting + 7 pitching
TIE_PROB = 0.03      # probability any single category ends in a tie

# If True, higher seed wins a tied playoff matchup (equal category wins).
# If False, coin flip.
PLAYOFF_HIGHER_SEED_WINS_TIE = True


# ============================================================
# SCHEDULE — 20 regular-season scoring periods
# Each entry: list of (away, home) tuples
# Home/away doesn't affect simulation (no home-field advantage).
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

def simulate_matchup(team_a, team_b, strengths):
    """
    Simulate one week's matchup between two teams.

    Uses Bradley-Terry model: for each of the 14 categories, team_a wins
    with probability (1 - TIE_PROB) * s_a / (s_a + s_b).

    Returns (wins_a, wins_b, ties).
    """
    s_a = strengths[team_a]
    s_b = strengths[team_b]
    p_a = (1.0 - TIE_PROB) * s_a / (s_a + s_b)
    p_b = (1.0 - TIE_PROB) * s_b / (s_a + s_b)
    # p_tie = TIE_PROB (implicit: 1 - p_a - p_b)

    wins_a = 0
    wins_b = 0
    ties = 0

    for _ in range(NUM_CATEGORIES):
        r = random.random()
        if r < p_a:
            wins_a += 1
        elif r < p_a + p_b:
            wins_b += 1
        else:
            ties += 1

    return wins_a, wins_b, ties


def simulate_regular_season(schedule, strengths):
    """
    Simulate the full 20-week regular season.

    Returns dict: team -> {"wins": int, "losses": int, "ties": int}
    where wins/losses/ties are cumulative category results across all weeks.
    (e.g., a team going 8-5-1 in week 1 and 10-4-0 in week 2 has record 18-9-1)
    """
    records = {team: {"wins": 0, "losses": 0, "ties": 0} for team in ALL_TEAMS}

    for week in schedule:
        for away, home in week:
            w_away, w_home, t = simulate_matchup(away, home, strengths)
            records[away]["wins"] += w_away
            records[away]["losses"] += w_home
            records[away]["ties"] += t
            records[home]["wins"] += w_home
            records[home]["losses"] += w_away
            records[home]["ties"] += t

    return records


def determine_playoff_seeds(records):
    """
    Determine 6 playoff seeds:
      Seeds 1-4: Division winners, ranked by regular-season record
      Seeds 5-6: Best non-division-winners (wild cards)

    Tiebreaker: random (consistent within a single call via pre-generated values).

    Returns (seeds_list, div_winners_dict).
    """
    # Pre-generate tiebreakers so sorting is consistent within this call
    tiebreakers = {team: random.random() for team in ALL_TEAMS}

    def sort_key(team):
        r = records[team]
        return (r["wins"], -r["losses"], tiebreakers[team])

    # Division winners
    div_winners = {}
    for div_name, teams in DIVISIONS.items():
        winner = max(teams, key=sort_key)
        div_winners[div_name] = winner

    # Rank division winners by record (seeds 1-4)
    div_winner_list = sorted(div_winners.values(), key=sort_key, reverse=True)

    # Wild cards: best 2 non-division-winners
    non_winners = [t for t in ALL_TEAMS if t not in div_winner_list]
    non_winners.sort(key=sort_key, reverse=True)
    wild_cards = non_winners[:2]

    seeds = div_winner_list + wild_cards
    return seeds, div_winners


def simulate_playoff_matchup(higher_seed, lower_seed, strengths):
    """
    Simulate a single playoff week between two teams.
    If category wins are equal, higher seed advances (configurable).
    """
    w_h, w_l, t = simulate_matchup(higher_seed, lower_seed, strengths)
    if w_h > w_l:
        return higher_seed
    elif w_l > w_h:
        return lower_seed
    else:
        if PLAYOFF_HIGHER_SEED_WINS_TIE:
            return higher_seed
        else:
            return random.choice([higher_seed, lower_seed])


def simulate_playoffs(seeds, strengths):
    """
    Simulate 3-round playoffs with reseeding.

      Round 1 (Wild Card):  Seed 3 vs 6, Seed 4 vs 5
      Round 2 (Semifinal):  Reseed remaining 4 — 1st vs 4th, 2nd vs 3rd
      Round 3 (Final):      Winners play for championship

    Returns the champion team name.
    """
    # Round 1: seeds 1-2 have bye
    r1_winner_a = simulate_playoff_matchup(seeds[2], seeds[5], strengths)
    r1_winner_b = simulate_playoff_matchup(seeds[3], seeds[4], strengths)

    # Round 2: Reseed — rank remaining 4 by original seed number
    remaining = [
        (0, seeds[0]),
        (1, seeds[1]),
        (seeds.index(r1_winner_a), r1_winner_a),
        (seeds.index(r1_winner_b), r1_winner_b),
    ]
    remaining.sort(key=lambda x: x[0])

    # Best remaining vs worst remaining, 2nd vs 3rd
    r2_winner_a = simulate_playoff_matchup(remaining[0][1], remaining[3][1], strengths)
    r2_winner_b = simulate_playoff_matchup(remaining[1][1], remaining[2][1], strengths)

    # Round 3: Championship
    # Determine higher seed for tiebreaker purposes
    idx_a = seeds.index(r2_winner_a)
    idx_b = seeds.index(r2_winner_b)
    if idx_a < idx_b:
        champion = simulate_playoff_matchup(r2_winner_a, r2_winner_b, strengths)
    else:
        champion = simulate_playoff_matchup(r2_winner_b, r2_winner_a, strengths)

    return champion


# ============================================================
# MONTE CARLO SIMULATION
# ============================================================

def run_simulations(n_sims, schedule, strengths, seed=None):
    """Run n_sims full-season simulations and accumulate stats."""
    if seed is not None:
        random.seed(seed)

    validate_schedule(schedule, ALL_TEAMS)

    stats = {team: {
        "total_wins": 0,
        "total_losses": 0,
        "total_ties": 0,
        "playoff_apps": 0,
        "div_titles": 0,
        "championships": 0,
        "seed_counts": defaultdict(int),
    } for team in ALL_TEAMS}

    for _ in range(n_sims):
        records = simulate_regular_season(schedule, strengths)
        seeds, div_winners = determine_playoff_seeds(records)
        champion = simulate_playoffs(seeds, strengths)

        # Accumulate regular season records
        for team in ALL_TEAMS:
            stats[team]["total_wins"] += records[team]["wins"]
            stats[team]["total_losses"] += records[team]["losses"]
            stats[team]["total_ties"] += records[team]["ties"]

        # Playoff appearances and seeding
        for i, team in enumerate(seeds):
            stats[team]["playoff_apps"] += 1
            stats[team]["seed_counts"][i + 1] += 1

        # Division titles
        for winner in div_winners.values():
            stats[winner]["div_titles"] += 1

        # Championship
        stats[champion]["championships"] += 1

    return stats


# ============================================================
# OUTPUT
# ============================================================

def print_results(stats, n_sims):
    """Print formatted simulation results."""
    print(f"\n{'=' * 80}")
    print(f"  SEASON SIMULATION RESULTS  ({n_sims:,} simulations)")
    print(f"{'=' * 80}")

    # Sort by championship %, then playoff %, then avg wins
    sorted_teams = sorted(
        ALL_TEAMS,
        key=lambda t: (
            stats[t]["championships"],
            stats[t]["playoff_apps"],
            stats[t]["total_wins"],
        ),
        reverse=True,
    )

    # Main table
    print(f"\n{'Team':<24} {'Avg Record':<16} {'Win%':>5}"
          f" {'Div%':>6} {'Playoff%':>9} {'Champ%':>7}")
    print(f"{'-' * 24} {'-' * 16} {'-' * 5}"
          f" {'-' * 6} {'-' * 9} {'-' * 7}")

    for team in sorted_teams:
        s = stats[team]
        avg_w = s["total_wins"] / n_sims
        avg_l = s["total_losses"] / n_sims
        avg_t = s["total_ties"] / n_sims
        total_decisions = avg_w + avg_l + avg_t
        win_pct = avg_w / total_decisions if total_decisions > 0 else 0
        div_pct = 100 * s["div_titles"] / n_sims
        playoff_pct = 100 * s["playoff_apps"] / n_sims
        champ_pct = 100 * s["championships"] / n_sims

        record_str = f"{avg_w:.1f}-{avg_l:.1f}-{avg_t:.1f}"
        print(f"{team:<24} {record_str:<16} {win_pct:.3f}"
              f" {div_pct:>5.1f}% {playoff_pct:>8.1f}% {champ_pct:>6.1f}%")

    # Division breakdown
    print(f"\n{'=' * 80}")
    print(f"  DIVISION BREAKDOWN")
    print(f"{'=' * 80}")

    for div_name, teams in DIVISIONS.items():
        print(f"\n  {div_name}")
        print(f"  {'Team':<24} {'Div%':>6} {'Playoff%':>9} {'Champ%':>7}")
        print(f"  {'-' * 24} {'-' * 6} {'-' * 9} {'-' * 7}")

        div_sorted = sorted(
            teams,
            key=lambda t: stats[t]["championships"],
            reverse=True,
        )
        for team in div_sorted:
            s = stats[team]
            div_pct = 100 * s["div_titles"] / n_sims
            playoff_pct = 100 * s["playoff_apps"] / n_sims
            champ_pct = 100 * s["championships"] / n_sims
            print(f"  {team:<24} {div_pct:>5.1f}% {playoff_pct:>8.1f}% {champ_pct:>6.1f}%")

    # Seed distribution
    print(f"\n{'=' * 80}")
    print(f"  SEED DISTRIBUTION (% of simulations)")
    print(f"{'=' * 80}")
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


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Fantasy Baseball Season Simulator")
    parser.add_argument(
        "--sims", type=int, default=10000,
        help="Number of simulations to run (default: 10000)",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for reproducibility",
    )
    args = parser.parse_args()

    print(f"Running {args.sims:,} season simulations...")
    if args.seed is not None:
        print(f"Random seed: {args.seed}")

    stats = run_simulations(args.sims, SCHEDULE, TEAM_STRENGTHS, seed=args.seed)
    print_results(stats, args.sims)


if __name__ == "__main__":
    main()
