# The Enterprise rules engine

`enterprise.py` is a deterministic Python state machine designed for bot-based testing. It implements setup, connections/capacity/lockdowns, influence/upkeep, asset acquisition and loss, Operations-card draw/economy, bids, private/public contract victory timing, and 2-player contracts.

Run the sample simulation:

```powershell
python enterprise.py
```

Use it from another script:

```python
from enterprise import Game, GreedyBot

game = Game(["A", "B", "C", "D"], seed=42)
winner = game.run(GreedyBot(), max_turns=1_000)
print(winner, game.turn_no)
```

For four-player testing, run `python simulate_four_players.py`. It pits a contract-rush bot, an income builder, a disruption-focused bot, and a second income builder over 1,000 deterministic seeds by default. Its report includes win shares, player-turn and round length, each winning contract/required Asset, and whether the winning contract was private, a public contract won by its original holder, or a public contract won by another player. The policies live in `bots.py` and can also be mixed per seat via `SeatPolicies`.

The supplied bots can initiate one bid per turn and can burn eligible Assets only after holding them through a prior turn.

Each bot evaluates all of its private contracts plus every public contract. It estimates distance as the required-Connection deficit plus the actions required to acquire or bid for the listed Asset, then targets the closest reachable contract (favoring its private contract only on an exact tie). Public contracts are not declared: once a bot meets one, it protects that position until its next turn, when the engine awards the win.

Each player is limited to eight Connections and may place only one Connection per turn. Bots remove a surplus Connection from a capacity-locked region when doing so reopens that region and leaves their currently relevant contract requirements intact; that ends their action phase as required by the rules.

Burns now accept target fields directly in their action dictionaries. For example, `{"kind":"burn", "asset":"ARMS DEPOT", "target_asset":"..."}` seizes an Asset in a region where the bot has a Connection; `SMUGGLING RING` accepts two `{player, region}` values in `targets`; and `STATE-ALIGNED MILITIA` accepts a locked `region`. The supplied bots choose targets for the targetable burns they use, prioritizing the current leader for disruptive effects and their contract/economy for non-disruptive effects.

To write a better bot, implement `choose_actions(game, player)` and `bid(game, bidder, defender, asset)`. `choose_actions` returns action dictionaries such as `{"kind": "place", "region": "ASIA"}`, `{"kind": "acquire", "asset": "..."}`, `{"kind": "bid", "asset": "..."}`, and `{"kind": "declare", "c": contract}`. Illegal actions safely raise `IllegalMove`; `Game.run` records no state change and continues, which makes exploratory bot policies simple.

Some effects inherently require a player choice (for example copying or targeting a card). The `play_op` and `burn` extension points are intentionally explicit so an informed policy adapter can supply those choices and any desired reaction-window behavior. The baseline bot uses only public board-state choices, making it suitable as a reproducible smoke-test opponent rather than as a strong player.
