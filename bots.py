"""Four-player-ready policies and a simple per-seat policy adapter with dynamic bidding logic."""
from __future__ import annotations

from enterprise import ASSET, Game, Policy, REGIONS

def asset_owner(game: Game, asset: str) -> str | None:
    return next((name for name, player in game.players.items() if asset in player.assets), None)

def legal_bid_target(game: Game, attacker: str, asset: str) -> bool:
    owner = asset_owner(game, asset)
    return bool(owner and owner != attacker and game.players[owner].first_turn_done and asset not in game.bid_protected)

def contract_distance(game: Game, player: str, contract) -> int:
    """Estimated actions needed: missing Connections plus obtaining its required Asset."""
    p = game.players[player]
    missing = sum(max(0, need - p.connections[region]) for region, need in contract.needs.items())
    asset_cost = 0
    if contract.asset not in p.assets:
        spec = ASSET[contract.asset]
        if contract.asset in game.pool:
            asset_cost = 1 if spec.region is None or p.connections[spec.region] else 2
        elif legal_bid_target(game, player, contract.asset):
            asset_cost = 1
        else:
            asset_cost = 6
    return missing + asset_cost

def closest_contract(game: Game, player: str):
    """Return (contract, is_private), favoring private contracts on exact ties."""
    p = game.players[player]
    candidates = [(c, True) for c in p.contracts] + [(c, False) for c in game.public_contracts]
    if not candidates:
        return None
    return min(candidates, key=lambda item: (contract_distance(game, player, item[0]), not item[1], item[0].asset))

def dynamic_bid_amount(game: Game, bidder: str, defender: str, asset: str, aggressiveness: float = 0.5) -> int:
    """Calculates dynamic bid valuation based on defensive necessity or offensive contract disruption."""
    b_player = game.players[bidder]
    d_player = game.players[defender] if defender in game.players else None
    
    # 1. Defending critical contract asset -> Spend everything
    if asset in b_player.assets:
        is_vital = any(c.asset == asset for c in b_player.contracts + game.public_contracts if game.contract_met(bidder, c) or contract_distance(game, bidder, c) <= 2)
        if is_vital:
            return b_player.influence

    # 2. Offensive Target: Disruption of Rival's Contract Asset
    if d_player and asset in d_player.assets:
        rival_needed = any(c.asset == asset for c in d_player.contracts + game.public_contracts)
        if rival_needed:
            # Willing to go all-in or up to 80-100% of influence to strip contract asset
            return max(1, int(b_player.influence * max(0.8, aggressiveness)))

    # 3. Opportunistic / General Acquisition -> Standard scaled valuation
    upkeep_value = ASSET[asset].upkeep
    scaled_bid = min(b_player.influence, int(upkeep_value + (b_player.influence * aggressiveness)))
    return max(1 if b_player.influence > 0 else 0, scaled_bid)

def goal_actions(game: Game, player: str, contract) -> list[dict]:
    """Actions that reduce the distance to a selected private or public contract."""
    p = game.players[player]
    actions = []
    spec = ASSET[contract.asset]
    if contract.asset not in p.assets:
        if contract.asset in game.pool:
            if spec.region and not p.connections[spec.region] and not game.locked(spec.region):
                actions.append({"kind": "place", "region": spec.region})
            elif spec.region is None or p.connections[spec.region]:
                actions.append({"kind": "acquire", "asset": contract.asset})
        elif legal_bid_target(game, player, contract.asset) and p.influence >= 2:
            action = {"kind": "bid", "asset": contract.asset}
            if "Backroom Deal" in p.hand:
                action["backroom"] = True
            elif "Cut Out" in p.hand:
                action["cut_out"] = True
            actions.append(action)
            
    for region, need in sorted(contract.needs.items(), key=lambda item: (p.connections[item[0]] - item[1], item[0])):
        if p.connections[region] < need and not game.locked(region):
            actions.append({"kind": "place", "region": region})
    return actions

def select_op_action(game: Game, player: str, target: str | None = None) -> dict | None:
    """Evaluates all Operations cards in hand and returns a prioritized play_op action."""
    p = game.players[player]
    if not p.hand:
        return None

    if not target:
        rivals = sorted(
            [x for x in game.players if x != player],
            key=lambda x: (len(game.players[x].assets), game.players[x].connections.total(), game.players[x].influence),
            reverse=True
        )
        target = rivals[0] if rivals else None

    if target:
        t_player = game.players[target]

        if "Regime Change" in p.hand:
            best_r = max(REGIONS, key=lambda r: t_player.connections[r])
            if t_player.connections[best_r] > 0:
                return {"kind": "play_op", "card": "Regime Change", "region": best_r}

        if "Shakedown" in p.hand and (t_player.influence > 0 or t_player.connections.total() > 0):
            return {"kind": "play_op", "card": "Shakedown", "player": target}

        if "Sanctions" in p.hand and t_player.assets:
            return {"kind": "play_op", "card": "Sanctions", "player": target}

        if "Asset Seizure" in p.hand and t_player.connections.total() > 0:
            return {"kind": "play_op", "card": "Asset Seizure", "player": target}

        if "Internal Purge" in p.hand and t_player.hand:
            return {"kind": "play_op", "card": "Internal Purge", "player": target}

    if "Shell Company" in p.hand:
        return {"kind": "play_op", "card": "Shell Company"}

    if "Cover Story" in p.hand:
        best_r = max(REGIONS, key=lambda r: p.connections[r])
        if p.connections[best_r] > 0 and (player, best_r) not in game.protected:
            return {"kind": "play_op", "card": "Cover Story", "region": best_r}

    if "Congressional Inquiry" in p.hand and not game.congress and target:
        best_r = max(REGIONS, key=lambda r: (game.players[target].connections[r], -p.connections[r]))
        if game.players[target].connections[best_r] > 0:
            return {"kind": "play_op", "card": "Congressional Inquiry", "region": best_r}

    return None

def locked_region_exit(game: Game, player: str) -> list[dict]:
    """Remove one surplus Connection to reopen a capacity-locked region."""
    p = game.players[player]
    contracts = p.contracts + game.public_contracts
    candidates = []
    for region in REGIONS:
        required = max((c.needs.get(region, 0) for c in contracts), default=0)
        if (game.total_connections(region) == game.capacity and game.congress != region
                and region not in game.forced_locks and p.connections[region] >= 2
                and p.connections[region] - 1 >= required):
            candidates.append(region)
    if not candidates:
        return []
    return [{"kind": "remove", "region": max(candidates, key=lambda r: (p.connections[r], r))}]

def one_connection(actions: list[dict]) -> list[dict]:
    """Keep only the first Connection placement, matching the per-turn rule."""
    placed = False
    result = []
    for action in actions:
        if action["kind"] == "place":
            if placed:
                continue
            placed = True
        result.append(action)
    return result

def opportunistic_burn(game: Game, player: str, disruptive: bool = False) -> list[dict]:
    """Return one legal, target-complete burn action with deterministic priorities."""
    p = game.players[player]
    contract_assets = {c.asset for c in p.contracts}
    eligible = p.assets & p.assets_at_previous_turn - contract_assets
    rivals = sorted((x for x in game.players if x != player), key=lambda x: (len(game.players[x].assets), game.players[x].connections.total(), game.players[x].influence), reverse=True)
    leader = rivals[0] if rivals else None

    if ("APPARATCHIK" in p.assets_at_previous_turn and "APPARATCHIK" in p.assets
            and "APPARATCHIK" not in contract_assets and sum(len(x.assets) for x in game.players.values()) >= 4):
        return [{"kind": "burn", "asset": "APPARATCHIK"}]
    if "ARMS DEPOT" in eligible:
        seize = [a for a in ASSET if legal_bid_target(game, player, a) and ASSET[a].region and p.connections[ASSET[a].region]]
        if seize:
            return [{"kind": "burn", "asset": "ARMS DEPOT", "target_asset": max(seize, key=lambda a: (ASSET[a].upkeep, a))}]
    if "INDEPENDENT TRADE UNION" in eligible and len(p.hand) >= 3:
        return [{"kind": "burn", "asset": "INDEPENDENT TRADE UNION"}]
    if "INTELLIGENCE LIAISON" in eligible and len(game.op_deck) >= 3:
        top = game.op_deck[-3:]
        discard = next((c for c in top if c not in {"Shell Company", "Plausible Deniability", "Double Cross"}), top[0])
        return [{"kind": "burn", "asset": "INTELLIGENCE LIAISON", "discard": discard}]
    if disruptive and "SMUGGLING RING" in eligible:
        targets = []
        for region in sorted(REGIONS, key=lambda r: max(game.players[x].connections[r] for x in rivals), reverse=True):
            victim = max(rivals, key=lambda x: game.players[x].connections[region])
            if game.players[victim].connections[region]:
                targets.append({"player": victim, "region": region})
            if len(targets) == 2:
                break
        if len(targets) == 2:
            return [{"kind": "burn", "asset": "SMUGGLING RING", "targets": targets}]
    if disruptive and "STATE-ALIGNED MILITIA" in eligible:
        locked = [r for r in REGIONS if game.locked(r) and sum(game.players[x].connections[r] for x in rivals)]
        if locked:
            return [{"kind": "burn", "asset": "STATE-ALIGNED MILITIA", "region": max(locked, key=lambda r: sum(game.players[x].connections[r] for x in rivals))}]
    if disruptive and "NON-ALIGNED BLOC" in eligible and sum(len(game.players[x].assets) for x in rivals) >= 3:
        return [{"kind": "burn", "asset": "NON-ALIGNED BLOC"}]
    if disruptive and "OFFSHORE FINANCE NETWORK" in eligible and leader:
        return [{"kind": "burn", "asset": "OFFSHORE FINANCE NETWORK", "player": leader}]
    if "OIL CONSORTIUM" in eligible and p.influence >= 5:
        return [{"kind": "burn", "asset": "OIL CONSORTIUM"}]
    return []

class SeatPolicies:
    """Lets a single game use a different policy for every seat."""
    def __init__(self, policies: dict[str, Policy]):
        self.policies = policies
    def choose_actions(self, game: Game, player: str):
        return self.policies[player].choose_actions(game, player)
    def bid(self, game: Game, bidder: str, defender: str, asset: str) -> int:
        return self.policies[bidder].bid(game, bidder, defender, asset)

class ContractRushBot:
    """Prioritizes its contract, but defends and bids dynamically on required contract assets."""
    def bid(self, game, bidder, defender, asset):
        return dynamic_bid_amount(game, bidder, defender, asset, aggressiveness=0.4)

    def choose_actions(self, game, player):
        p = game.players[player]
        for contract in p.contracts:
            if game.contract_met(player, contract):
                return [{"kind": "declare", "c": contract}]
        if any(game.contract_met(player, c) for c in game.public_contracts):
            return []
        exit_action = locked_region_exit(game, player)
        if exit_action:
            return exit_action
        choice = closest_contract(game, player)
        actions = goal_actions(game, player, choice[0]) if choice else []
        
        op_action = select_op_action(game, player)
        if op_action:
            actions.append(op_action)

        return one_connection(actions + opportunistic_burn(game, player))[:4]

class IncomeBot:
    """Builds economy, but targets rival contract assets aggressively when rich in influence."""
    def bid(self, game, bidder, defender, asset):
        return dynamic_bid_amount(game, bidder, defender, asset, aggressiveness=0.6)

    def choose_actions(self, game, player):
        p = game.players[player]
        declarations = [{"kind": "declare", "c": c} for c in p.contracts if game.contract_met(player, c)]
        if declarations:
            return declarations
        if any(game.contract_met(player, c) for c in game.public_contracts):
            return []
        exit_action = locked_region_exit(game, player)
        if exit_action:
            return exit_action
        
        actions = []
        op_action = select_op_action(game, player)
        if op_action:
            actions.append(op_action)

        choice = closest_contract(game, player)
        if choice:
            actions.extend(goal_actions(game, player, choice[0]))
            
        legal_assets = [a for a in game.pool if (ASSET[a].region is None or p.connections[ASSET[a].region]) and p.influence >= ASSET[a].upkeep]
        if not actions and legal_assets:
            actions.append({"kind": "acquire", "asset": min(legal_assets, key=lambda a: (ASSET[a].upkeep, a))})
        
        open_regions = [r for r in REGIONS if not game.locked(r)]
        open_regions.sort(key=lambda r: (game.total_connections(r), r))
        actions.extend({"kind": "place", "region": r} for r in open_regions[:2])
        
        # Check for hostile bid targeting opponent contract requirements
        rivals = [x for x in game.players if x != player]
        rival_needed_assets = [
            a for r in rivals for c in game.players[r].contracts + game.public_contracts
            if (a := c.asset) in game.players[r].assets and legal_bid_target(game, player, a)
        ]
        
        target_bid_asset = rival_needed_assets[0] if rival_needed_assets else None
        if not target_bid_asset:
            targets = [a for a in ASSET if legal_bid_target(game, player, a) and p.influence >= ASSET[a].upkeep + 2]
            target_bid_asset = max(targets, key=lambda a: (ASSET[a].upkeep, a)) if targets else None

        if target_bid_asset and p.influence >= 2:
            bid_act = {"kind": "bid", "asset": target_bid_asset}
            if "Backroom Deal" in p.hand:
                bid_act["backroom"] = True
            elif "Cut Out" in p.hand:
                bid_act["cut_out"] = True
            actions.append(bid_act)
            
        return one_connection(actions + opportunistic_burn(game, player))[:4]

class DisruptorBot:
    """Aggressively targets opponent contract assets and defends its own required assets with full influence."""
    def bid(self, game, bidder, defender, asset):
        return dynamic_bid_amount(game, bidder, defender, asset, aggressiveness=0.9)

    def choose_actions(self, game, player):
        p = game.players[player]
        declarations = [{"kind": "declare", "c": c} for c in p.contracts if game.contract_met(player, c)]
        if declarations:
            return declarations
            
        rivals = sorted((x for x in game.players if x != player), key=lambda x: (len(game.players[x].assets), game.players[x].connections.total(), game.players[x].influence), reverse=True)
        target = rivals[0] if rivals else None

        if any(game.contract_met(player, c) for c in game.public_contracts):
            return []
        exit_action = locked_region_exit(game, player)
        if exit_action:
            return exit_action
            
        choice = closest_contract(game, player)
        actions = goal_actions(game, player, choice[0]) if choice else []
        legal_assets = [a for a in game.pool if (ASSET[a].region is None or p.connections[ASSET[a].region]) and p.influence >= ASSET[a].upkeep]
        if not actions and legal_assets:
            actions.append({"kind": "acquire", "asset": min(legal_assets, key=lambda a: (ASSET[a].upkeep, a))})
            
        open_regions = sorted((r for r in REGIONS if not game.locked(r) and game.total_connections(r) < game.capacity - 1), key=game.total_connections)
        actions.extend({"kind": "place", "region": r} for r in open_regions[:2])

        op_action = select_op_action(game, player, target)
        if op_action:
            actions.append(op_action)
        elif len(p.hand) < 3 and p.influence >= 1:
            actions.append({"kind": "buy_op"})

        # Always favor bidding on an opponent's needed contract asset over general assets
        if target:
            target_player = game.players[target]
            needed_assets = [c.asset for c in target_player.contracts + game.public_contracts if c.asset in target_player.assets and legal_bid_target(game, player, c.asset)]
            other_assets = [a for a in target_player.assets if legal_bid_target(game, player, a)]
            
            chosen_bid_asset = needed_assets[0] if needed_assets else (other_assets[0] if other_assets else None)
            if chosen_bid_asset and p.influence >= 2:
                bid_act = {"kind": "bid", "asset": chosen_bid_asset}
                if "Backroom Deal" in p.hand:
                    bid_act["backroom"] = True
                elif "Cut Out" in p.hand:
                    bid_act["cut_out"] = True
                actions.append(bid_act)

        return (actions + opportunistic_burn(game, player, disruptive=True))[:4]

class OpportunistBot:
    """Scales bidding intensity based on threat levels, bidding maximum influence to strip leader contract assets."""
    def bid(self, game, bidder, defender, asset):
        rivals = [x for x in game.players if x != bidder]
        leader = max(rivals, key=lambda x: (len(game.players[x].assets), game.players[x].influence)) if rivals else None
        
        # Scale aggressiveness way up if defender is the leader or threatened player
        aggressiveness = 0.95 if defender == leader else 0.5
        return dynamic_bid_amount(game, bidder, defender, asset, aggressiveness=aggressiveness)

    def choose_actions(self, game, player):
        p = game.players[player]
        declarations = [{"kind": "declare", "c": c} for c in p.contracts if game.contract_met(player, c)]
        if declarations:
            return declarations
        if any(game.contract_met(player, c) for c in game.public_contracts):
            return []
        exit_action = locked_region_exit(game, player)
        if exit_action:
            return exit_action

        choice = closest_contract(game, player)
        actions = goal_actions(game, player, choice[0]) if choice else []
        legal_assets = [a for a in game.pool if (ASSET[a].region is None or p.connections[ASSET[a].region]) and p.influence >= ASSET[a].upkeep]
        if not actions and legal_assets:
            actions.append({"kind": "acquire", "asset": min(legal_assets, key=lambda a: (ASSET[a].upkeep, a))})
            
        open_regions = [r for r in REGIONS if not game.locked(r)]
        open_regions.sort(key=lambda r: (game.total_connections(r), r))
        actions.extend({"kind": "place", "region": r} for r in open_regions[:2])

        rivals = sorted((x for x in game.players if x != player), key=lambda x: (len(game.players[x].assets), game.players[x].connections.total(), game.players[x].influence), reverse=True)
        leader = rivals[0] if rivals else None
        leader_choice = closest_contract(game, leader) if leader else None
        threatened = leader_choice is not None and contract_distance(game, leader, leader_choice[0]) <= 1

        op_action = select_op_action(game, player, leader)
        if op_action:
            actions.append(op_action)

        if threatened and leader:
            wanted = leader_choice[0].asset
            if wanted in game.players[leader].assets and legal_bid_target(game, player, wanted) and p.influence >= 2:
                bid_act = {"kind": "bid", "asset": wanted}
                if "Backroom Deal" in p.hand:
                    bid_act["backroom"] = True
                elif "Cut Out" in p.hand:
                    bid_act["cut_out"] = True
                actions.append(bid_act)
        else:
            targets = [a for a in ASSET if legal_bid_target(game, player, a) and p.influence >= ASSET[a].upkeep + 2]
            if targets:
                bid_act = {"kind": "bid", "asset": max(targets, key=lambda a: (ASSET[a].upkeep, a))}
                if "Backroom Deal" in p.hand:
                    bid_act["backroom"] = True
                elif "Cut Out" in p.hand:
                    bid_act["cut_out"] = True
                actions.append(bid_act)

        return (actions + opportunistic_burn(game, player, disruptive=threatened))[:4]