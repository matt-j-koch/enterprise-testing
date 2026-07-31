import unittest
from enterprise import Game, GreedyBot, IllegalMove, REGIONS, ContractSpec, MAX_CONNECTIONS_PER_PLAYER
from bots import closest_contract, locked_region_exit

class EngineTests(unittest.TestCase):
    def test_lockdown_blocks_income_and_new_connection(self):
        g=Game(["A","B"],seed=1)
        # Isolate the rule from randomized setup.
        for p in g.players.values(): p.connections.clear(); p.assets.clear(); p.influence=0
        g.pool.clear(); g.congress=None; g.turn_index=0
        for _ in range(g.capacity): g.players["A"].connections["ASIA"]+=1
        self.assertTrue(g.locked("ASIA"))
        g.begin_turn()
        self.assertEqual(g.players["A"].influence,0)
        with self.assertRaises(IllegalMove): g.place("A","ASIA")

    def test_bid_tie_defender_keeps_asset(self):
        g=Game(["A","B"],seed=2)
        asset=next(iter(g.players["A"].assets))
        g.players["A"].first_turn_done=True
        g.players["A"].influence=g.players["B"].influence=2
        class TieBot:
            def bid(self,*_): return 2
            def choose_actions(self,*_): return []
        g.turn_index=1
        g.bid("B",asset,TieBot())
        self.assertIn(asset,g.players["A"].assets)

    def test_many_seeded_games_terminate_or_reach_limit_cleanly(self):
        outcomes=[Game(["A","B","C"],seed=s).run(GreedyBot(),150) for s in range(20)]
        self.assertTrue(all(x in {"A","B","C",None} for x in outcomes))

    def test_four_player_setup_is_valid_across_many_seeds(self):
        for seed in range(250):
            game=Game(["A","B","C","D"],seed=seed)
            self.assertTrue(all(game.total_connections(r)<=game.capacity for r in REGIONS))

    def test_asset_must_be_held_through_a_prior_turn_before_burning(self):
        g=Game(["A","B"],seed=2)
        asset=next(iter(g.players["A"].assets))
        with self.assertRaises(IllegalMove): g.burn("A",asset)

    def test_connection_income_arrives_before_upkeep(self):
        g=Game(["A","B"],seed=3)
        for p in g.players.values(): p.connections.clear(); p.assets.clear(); p.influence=0
        g.pool.discard("CARTEL NETWORK")
        g.players["A"].assets.add("CARTEL NETWORK")
        g.players["A"].connections["LATIN AMERICA"] = 1
        g.begin_turn()
        self.assertIn("CARTEL NETWORK", g.players["A"].assets)
        self.assertEqual(g.players["A"].influence, 0)  # 1 income, then 1 upkeep

    def test_closest_contract_can_prefer_public_goal(self):
        g=Game(["A","B"],seed=4)
        p=g.players["A"]
        p.assets={"CARTEL NETWORK"}; p.connections.clear(); p.connections["LATIN AMERICA"]=2; p.connections["EUROPE"]=1
        private=ContractSpec("CENTRAL AMERICAN GUERILLAS", {"USSR":2})
        public=ContractSpec("CARTEL NETWORK", {"LATIN AMERICA":2,"EUROPE":1})
        p.contracts=[private]; g.public_contracts=[public]
        self.assertEqual(closest_contract(g,"A"),(public,False))

    def test_connection_cap_is_eight(self):
        g=Game(["A","B"],seed=5)
        p=g.players["A"]; p.connections.clear(); p.connections["ASIA"]=MAX_CONNECTIONS_PER_PLAYER
        with self.assertRaises(IllegalMove): g.place("A","EUROPE")

    def test_only_one_connection_can_be_placed_per_turn(self):
        g=Game(["A","B"],seed=5)
        g.players["A"].connections.clear(); g.players["A"].influence=3
        g.place("A","EUROPE")
        with self.assertRaises(IllegalMove): g.place("A","USSR")

    def test_bot_removes_surplus_to_reopen_capacity_lock(self):
        g=Game(["A","B"],seed=6)
        for p in g.players.values(): p.connections.clear()
        g.players["A"].connections["ASIA"]=2; g.players["B"].connections["ASIA"]=1
        self.assertEqual(g.total_connections("ASIA"),g.capacity)
        self.assertEqual(locked_region_exit(g,"A"),[{"kind":"remove","region":"ASIA"}])

if __name__ == "__main__": unittest.main()
