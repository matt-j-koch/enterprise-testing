"""Run a reproducible four-seat bot tournament: python simulate_four_players.py"""
from collections import Counter
from enterprise import Game, contract_id
from bots import ContractRushBot, DisruptorBot, IncomeBot, SeatPolicies

SEATS = ["Rush", "Income", "Disrupt", "Income 2"]
POLICY = SeatPolicies({"Rush":ContractRushBot(), "Income":IncomeBot(), "Disrupt":DisruptorBot(), "Income 2":IncomeBot()})

def run(games=1_000, max_turns=300):
    wins, turns, contracts, assets, origin = Counter(), [], Counter(), Counter(), Counter()
    for seed in range(games):
        game=Game(SEATS, seed=seed)
        winner=game.run(POLICY, max_turns=max_turns)
        wins[winner or "No winner"] += 1; turns.append(game.turn_no)
        if winner and game.victory_contract:
            contract=game.victory_contract
            contracts[contract.asset] += 1; assets[contract.asset] += 1
            owner=game.contract_origin.get(contract_id(contract))
            if game.victory_was_public:
                origin["Public contract — original holder"] += winner == owner
                origin["Public contract — another player"] += winner != owner
            else: origin["Private contract — original holder"] += 1
    print(f"games={games}; average player turns={sum(turns)/len(turns):.1f}; average rounds={sum(turns)/len(turns)/len(SEATS):.1f}")
    print("\nWins by seat")
    for name in SEATS+["No winner"]:
        print(f"{name:10} {wins[name]:3}  ({wins[name]/games:.1%})")
    print("\nWinning contracts / required Assets")
    for name,count in contracts.most_common():
        print(f"{name:30} {count:4}  ({count/games:.1%})")
    print("\nContract origin at victory")
    for label,count in origin.items():
        print(f"{label:35} {count:4}  ({count/games:.1%})")

if __name__ == "__main__": run()
