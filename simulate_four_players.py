"""Run a customizable seat bot tournament: python simulate_four_players.py --seats Rush Disrupt Income Opportunist"""
import argparse
from collections import Counter
from enterprise import Game, contract_id
from bots import ContractRushBot, DisruptorBot, IncomeBot, OpportunistBot, SeatPolicies

# Mapping available bot names to their instantiation functions/classes
AVAILABLE_BOTS = {
    "Disrupt": DisruptorBot,
    "Rush": ContractRushBot,
    "Income": IncomeBot,
    "Opportunist": OpportunistBot,
}

def parse_args():
    parser = argparse.ArgumentParser(description="Run a customizable bot tournament.")
    parser.add_argument(
        "--seats",
        nargs="+",
        default=["Disrupt", "Rush", "Opportunist", "Income"],
        choices=list(AVAILABLE_BOTS.keys()),
        help="Specify the bots and their seat order (e.g., --seats Rush Disrupt Income)"
    )
    parser.add_argument("--games", type=int, default=1_000, help="Number of games to simulate")
    parser.add_argument("--max-turns", type=int, default=300, help="Maximum allowed turns per game")
    return parser.parse_args()

def run(seats, games=1_000, max_turns=300):
    # Dynamically build seat policies and unique seat names to prevent duplicates in seat labels
    seat_names = []
    policy_dict = {}
    
    for i, bot_key in enumerate(seats):
        # Append index to handle duplicate bot selections gracefully (e.g., "Rush_1", "Rush_2")
        seat_label = f"{bot_key}_{i+1}" if seats.count(bot_key) > 1 else bot_key
        seat_names.append(seat_label)
        policy_dict[seat_label] = AVAILABLE_BOTS[bot_key]()

    policy = SeatPolicies(policy_dict)

    wins, turns, contracts, assets, origin = Counter(), [], Counter(), Counter(), Counter()
    
    for seed in range(games):
        game = Game(seat_names, seed=seed)
        winner = game.run(policy, max_turns=max_turns)
        wins[winner or "No winner"] += 1
        turns.append(game.turn_no)
        
        if winner and game.victory_contract:
            contract = game.victory_contract
            contracts[contract.asset] += 1
            assets[contract.asset] += 1
            owner = game.contract_origin.get(contract_id(contract))
            if game.victory_was_public:
                origin["Public contract — original holder"] += (winner == owner)
                origin["Public contract — another player"] += (winner != owner)
            else:
                origin["Private contract — original holder"] += 1

    print(f"games={games}; average player turns={sum(turns)/len(turns):.1f}; average rounds={sum(turns)/len(turns)/len(seat_names):.1f}")
    print("\nWins by seat")
    for name in seat_names + ["No winner"]:
        print(f"{name:13} {wins[name]:3}  ({wins[name]/games:.1%})")
    print("\nWinning contracts / required Assets")
    for name, count in contracts.most_common():
        print(f"{name:30} {count:4}  ({count/games:.1%})")
    print("\nContract origin at victory")
    for label, count in origin.items():
        print(f"{label:35} {count:4}  ({count/games:.1%})")

if __name__ == "__main__":
    args = parse_args()
    run(seats=args.seats, games=args.games, max_turns=args.max_turns)