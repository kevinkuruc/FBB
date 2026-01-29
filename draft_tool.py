#!/usr/bin/env python3
"""
Fantasy Baseball Draft Tool

Calculates marginal value of each player based on expected category wins.
Updates rankings dynamically as players are drafted.
"""

import csv
import math
from typing import List, Dict, Optional

# =============================================================================
# CONSTANTS
# =============================================================================

NUM_WEEKS = 25
NUM_ROSTER_SPOTS = 9

# Weekly standard deviations from 2024 league data
WEEKLY_SD = {
    'R': 6.03,
    'HR': 2.93,
    'RBI': 6.72,
    'SB': 2.57,
    'SO': 7.45,
    'TB': 15.94,
    'OBP': 0.04
}

# League average weekly totals from 2024 data
LEAGUE_AVG_WEEKLY = {
    'R': 28.96,
    'HR': 8.02,
    'RBI': 27.86,
    'SB': 4.74,
    'SO': 50.11,
    'TB': 88.87,
    'OBP': 0.32
}

# Replacement level (average of players ranked 145-160, scaled up by 1.263 for realistic baseline)
# Scale factor calibrated so starting with 9 replacement players gives ~45% SO win probability
SCALE_FACTOR = 1.263
REPLACEMENT_LEVEL = {
    'PA': round(505.5 * SCALE_FACTOR),
    'R': round(60.8 * SCALE_FACTOR),
    'HR': round(16.8 * SCALE_FACTOR),
    'RBI': round(60.1 * SCALE_FACTOR),
    'SO': round(113.1 * SCALE_FACTOR),
    'TB': round(185.9 * SCALE_FACTOR),
    'SB': round(8.8 * SCALE_FACTOR),
    'OBP': 0.312
}

# Categories where lower is better
NEGATIVE_CATS = {'SO'}

# =============================================================================
# MATH HELPERS
# =============================================================================

def normal_cdf(x: float) -> float:
    """Standard normal CDF using error function approximation."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def win_probability(my_mean: float, opp_mean: float, sd: float, lower_is_better: bool = False) -> float:
    """
    Calculate probability of winning a category.

    Assumes both teams' weekly totals are normally distributed with the same SD.
    P(my > opp) = Φ((my_mean - opp_mean) / (sd * √2))

    For categories where lower is better (like SO):
    P(my < opp) = Φ((opp_mean - my_mean) / (sd * √2))
    """
    if lower_is_better:
        z = (opp_mean - my_mean) / (sd * math.sqrt(2))
    else:
        z = (my_mean - opp_mean) / (sd * math.sqrt(2))
    return normal_cdf(z)


# =============================================================================
# PLAYER CLASS
# =============================================================================

class Player:
    def __init__(self, data: Dict):
        self.name = data['Name']
        self.pa = int(data['PA'])
        self.r = int(data['R'])
        self.hr = int(data['HR'])
        self.rbi = int(data['RBI'])
        self.so = int(data['SO'])
        self.tb = int(data['TB'])
        self.sb = int(data['SB'])
        self.obp = float(data['OBP'])
        self.z_total = float(data['zTotal'])

        # Weekly projections
        self.weekly = {
            'R': self.r / NUM_WEEKS,
            'HR': self.hr / NUM_WEEKS,
            'RBI': self.rbi / NUM_WEEKS,
            'SB': self.sb / NUM_WEEKS,
            'SO': self.so / NUM_WEEKS,
            'TB': self.tb / NUM_WEEKS,
            'OBP': self.obp
        }

    def __repr__(self):
        return f"Player({self.name})"


def create_replacement_player() -> Player:
    """Create a replacement-level player from constants."""
    data = {
        'Name': 'REPLACEMENT',
        'PA': REPLACEMENT_LEVEL['PA'],
        'R': REPLACEMENT_LEVEL['R'],
        'HR': REPLACEMENT_LEVEL['HR'],
        'RBI': REPLACEMENT_LEVEL['RBI'],
        'SO': REPLACEMENT_LEVEL['SO'],
        'TB': REPLACEMENT_LEVEL['TB'],
        'SB': REPLACEMENT_LEVEL['SB'],
        'OBP': REPLACEMENT_LEVEL['OBP'],
        'zTotal': 0.0
    }
    return Player(data)


# =============================================================================
# ROSTER CLASS
# =============================================================================

class Roster:
    def __init__(self, num_spots: int = NUM_ROSTER_SPOTS):
        self.num_spots = num_spots
        self.players: List[Player] = []
        self.replacement = create_replacement_player()

    def add_player(self, player: Player):
        """Add a player to the roster."""
        if len(self.players) >= self.num_spots:
            raise ValueError("Roster is full!")
        self.players.append(player)

    def remove_player(self, player_name: str) -> Optional[Player]:
        """Remove a player from the roster by name."""
        for i, p in enumerate(self.players):
            if p.name == player_name:
                return self.players.pop(i)
        return None

    def get_weekly_projections(self) -> Dict[str, float]:
        """
        Calculate team's weekly projections for each category.

        For counting stats: sum of all players' weekly contributions
        For OBP: average of all players' OBPs (simplified /9 model)
        """
        # Fill empty slots with replacement players
        num_drafted = len(self.players)
        num_replacement = self.num_spots - num_drafted

        projections = {}

        # Counting stats: sum weekly contributions
        for cat in ['R', 'HR', 'RBI', 'SB', 'SO', 'TB']:
            total = sum(p.weekly[cat] for p in self.players)
            total += num_replacement * self.replacement.weekly[cat]
            projections[cat] = total

        # OBP: average (simplified model)
        obp_sum = sum(p.obp for p in self.players)
        obp_sum += num_replacement * self.replacement.obp
        projections['OBP'] = obp_sum / self.num_spots

        return projections

    def get_expected_wins(self) -> Dict[str, float]:
        """
        Calculate expected category wins per week.

        Returns dict with P(win) for each category and total expected wins.
        """
        projections = self.get_weekly_projections()

        wins = {}
        total = 0.0

        for cat in ['R', 'HR', 'RBI', 'SB', 'SO', 'TB', 'OBP']:
            lower_is_better = cat in NEGATIVE_CATS
            p_win = win_probability(
                my_mean=projections[cat],
                opp_mean=LEAGUE_AVG_WEEKLY[cat],
                sd=WEEKLY_SD[cat],
                lower_is_better=lower_is_better
            )
            wins[cat] = p_win
            total += p_win

        wins['TOTAL'] = total
        return wins

    def get_roster_summary(self) -> str:
        """Return a formatted string summarizing the roster."""
        lines = []
        lines.append("\n" + "=" * 70)
        lines.append("YOUR ROSTER")
        lines.append("=" * 70)

        if not self.players:
            lines.append("  (empty - 9 replacement-level players)")
        else:
            for i, p in enumerate(self.players, 1):
                lines.append(f"  {i}. {p.name:<25} (zTotal: {p.z_total:.2f})")
            remaining = self.num_spots - len(self.players)
            if remaining > 0:
                lines.append(f"  ... {remaining} replacement-level slots remaining")

        # Show projections
        proj = self.get_weekly_projections()
        wins = self.get_expected_wins()

        lines.append("\nWeekly Projections vs League Avg:")
        lines.append("-" * 70)
        lines.append(f"{'Cat':<6} {'Your Team':>10} {'Lg Avg':>10} {'P(Win)':>10}")
        lines.append("-" * 70)

        for cat in ['R', 'HR', 'RBI', 'SO', 'TB', 'SB', 'OBP']:
            my_val = proj[cat]
            lg_val = LEAGUE_AVG_WEEKLY[cat]
            p_win = wins[cat]

            if cat == 'OBP':
                lines.append(f"{cat:<6} {my_val:>10.3f} {lg_val:>10.3f} {p_win:>10.1%}")
            else:
                lines.append(f"{cat:<6} {my_val:>10.1f} {lg_val:>10.1f} {p_win:>10.1%}")

        lines.append("-" * 70)
        lines.append(f"{'TOTAL':<6} {'':<10} {'':<10} {wins['TOTAL']:>10.2f} expected wins/week")
        lines.append("=" * 70)

        return "\n".join(lines)


# =============================================================================
# DRAFT TOOL
# =============================================================================

class DraftTool:
    def __init__(self, players_file: str, top_n: int = 300):
        self.roster = Roster()
        self.available: List[Player] = []
        self.drafted_names: set = set()

        # Load players
        with open(players_file, 'r') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= top_n:
                    break
                self.available.append(Player(row))

        print(f"Loaded {len(self.available)} players")

    def calculate_marginal_value(self, player: Player) -> float:
        """
        Calculate the marginal value of adding a player to the roster.

        Marginal value = expected wins with player - expected wins without
        """
        if len(self.roster.players) >= self.roster.num_spots:
            return 0.0

        # Current expected wins
        current_wins = self.roster.get_expected_wins()['TOTAL']

        # Temporarily add player
        self.roster.players.append(player)
        new_wins = self.roster.get_expected_wins()['TOTAL']
        self.roster.players.pop()

        return new_wins - current_wins

    def get_ranked_available(self) -> List[tuple]:
        """
        Return available players ranked by marginal value.

        Returns list of (player, marginal_value) tuples.
        """
        available = [p for p in self.available if p.name not in self.drafted_names]

        ranked = []
        for player in available:
            mv = self.calculate_marginal_value(player)
            ranked.append((player, mv))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked

    def draft_player(self, player_name: str) -> bool:
        """
        Draft a player by name.

        Returns True if successful, False if player not found or already drafted.
        """
        for player in self.available:
            if player.name.lower() == player_name.lower():
                if player.name in self.drafted_names:
                    print(f"  {player.name} has already been drafted!")
                    return False

                self.roster.add_player(player)
                self.drafted_names.add(player.name)
                print(f"  ✓ Drafted {player.name}")
                return True

        print(f"  Player '{player_name}' not found in top 300")
        return False

    def mark_drafted(self, player_name: str) -> bool:
        """
        Mark a player as drafted by another team (removes from available).
        """
        for player in self.available:
            if player.name.lower() == player_name.lower():
                if player.name in self.drafted_names:
                    print(f"  {player.name} has already been drafted!")
                    return False

                self.drafted_names.add(player.name)
                print(f"  ✓ Marked {player.name} as drafted by opponent")
                return True

        print(f"  Player '{player_name}' not found in top 300")
        return False

    def show_top_available(self, n: int = 25):
        """Display top N available players by marginal value."""
        ranked = self.get_ranked_available()[:n]

        print("\n" + "=" * 90)
        print(f"TOP {n} AVAILABLE PLAYERS (by Marginal Value)")
        print("=" * 90)
        print(f"{'Rank':<5} {'Name':<25} {'MargVal':>8} {'zTotal':>7} {'R':>4} {'HR':>4} {'RBI':>4} {'SO':>4} {'TB':>4} {'SB':>4} {'OBP':>5}")
        print("-" * 90)

        for i, (player, mv) in enumerate(ranked, 1):
            print(f"{i:<5} {player.name:<25} {mv:>8.4f} {player.z_total:>7.2f} "
                  f"{player.r:>4} {player.hr:>4} {player.rbi:>4} {player.so:>4} "
                  f"{player.tb:>4} {player.sb:>4} {player.obp:>5.3f}")

        print("=" * 90)

    def show_category_values(self, n: int = 10):
        """Show top players for each category by marginal value contribution."""
        ranked = self.get_ranked_available()

        # For each category, show who would help most
        print("\n" + "=" * 70)
        print("TOP PLAYERS BY CATEGORY NEED")
        print("=" * 70)

        current_proj = self.roster.get_weekly_projections()
        current_wins = self.roster.get_expected_wins()

        for cat in ['R', 'HR', 'RBI', 'SO', 'TB', 'SB', 'OBP']:
            print(f"\n{cat} (current P(win): {current_wins[cat]:.1%}):")

            # Calculate category-specific value for each player
            cat_values = []
            for player, total_mv in ranked[:50]:  # Check top 50 by total MV
                # Temporarily add player and see category improvement
                self.roster.players.append(player)
                new_wins = self.roster.get_expected_wins()
                cat_improvement = new_wins[cat] - current_wins[cat]
                self.roster.players.pop()
                cat_values.append((player, cat_improvement))

            cat_values.sort(key=lambda x: x[1], reverse=True)

            for player, imp in cat_values[:5]:
                print(f"  {player.name:<25} +{imp:.2%}")

    def run_interactive(self):
        """Run the interactive draft interface."""
        print("\n" + "=" * 70)
        print("FANTASY BASEBALL DRAFT TOOL")
        print("=" * 70)
        print("\nCommands:")
        print("  draft <name>  - Draft a player to your team")
        print("  take <name>   - Mark a player as drafted by opponent")
        print("  top [n]       - Show top N available players (default 25)")
        print("  roster        - Show your current roster")
        print("  cats          - Show top players by category need")
        print("  search <term> - Search for a player by name")
        print("  quit          - Exit the tool")
        print("=" * 70)

        while True:
            try:
                cmd = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not cmd:
                continue

            parts = cmd.split(maxsplit=1)
            action = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if action == 'quit' or action == 'exit':
                print("Goodbye!")
                break

            elif action == 'draft':
                if not arg:
                    print("  Usage: draft <player name>")
                else:
                    self.draft_player(arg)

            elif action == 'take':
                if not arg:
                    print("  Usage: take <player name>")
                else:
                    self.mark_drafted(arg)

            elif action == 'top':
                n = int(arg) if arg.isdigit() else 25
                self.show_top_available(n)

            elif action == 'roster':
                print(self.roster.get_roster_summary())

            elif action == 'cats':
                self.show_category_values()

            elif action == 'search':
                if not arg:
                    print("  Usage: search <term>")
                else:
                    term = arg.lower()
                    matches = [p for p in self.available
                              if term in p.name.lower() and p.name not in self.drafted_names]
                    if matches:
                        print(f"\n  Found {len(matches)} matches:")
                        for p in matches[:10]:
                            mv = self.calculate_marginal_value(p)
                            print(f"    {p.name:<25} MargVal: {mv:.4f}, zTotal: {p.z_total:.2f}")
                    else:
                        print(f"  No available players matching '{arg}'")

            else:
                print(f"  Unknown command: {action}")
                print("  Type 'quit' to exit, or use: draft, take, top, roster, cats, search")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    tool = DraftTool('/home/user/FBB/fantasy_hitters_2026.csv', top_n=300)

    # Show initial state
    print(tool.roster.get_roster_summary())
    tool.show_top_available(15)

    # Run interactive mode
    tool.run_interactive()
