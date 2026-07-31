"""Four-player-ready policies and a simple per-seat policy adapter."""
from __future__ import annotations

from enterprise import ASSET, Game, Policy, REGIONS

def asset_owner(game: Game, asset: str) -> str | None:
    return next((name for name, player in game.players.items() if asset in player.assets), None)

def legal_bid_target(game: Game, attacker: str, asset: str) -> bool:
    owner=asset_owner(game, asset)
    return bool(owner and owner != attacker and game.players[owner].first_turn_done and asset not in game.bid_protected)

def contract_distance(game: Game, player: str, contract) -> int:
    """Estimated actions needed: missing Connections plus obtaining its required Asset."""
    p=game.players[player]
    missing=sum(max(0, need-p.connections[region]) for region,need in contract.needs.items())
    asset_cost=0
    if contract.asset not in p.assets:
        spec=ASSET[contract.asset]
        if contract.asset in game.pool:
            # A regional Connection is needed before the buy can occur.
            asset_cost=1 if spec.region is None or p.connections[spec.region] else 2
        elif legal_bid_target(game,player,contract.asset): asset_cost=1
        else: asset_cost=6  # temporarily unreachable assets rank behind reachable goals
    return missing+asset_cost

def closest_contract(game: Game, player: str):
    """Return (contract, is_private), favoring private contracts on exact ties."""
    p=game.players[player]
    candidates=[(c,True) for c in p.contracts]+[(c,False) for c in game.public_contracts]
    if not candidates: return None
    return min(candidates,key=lambda item:(contract_distance(game,player,item[0]),not item[1],item[0].asset))

def goal_actions(game: Game, player: str, contract) -> list[dict]:
    """Actions that reduce the distance to a selected private or public contract."""
    p=game.players[player]; actions=[]; spec=ASSET[contract.asset]
    if contract.asset not in p.assets:
        if contract.asset in game.pool:
            if spec.region and not p.connections[spec.region] and not game.locked(spec.region):
                actions.append({"kind":"place","region":spec.region})
            elif spec.region is None or p.connections[spec.region]:
                actions.append({"kind":"acquire","asset":contract.asset})
        elif legal_bid_target(game,player,contract.asset) and p.influence>=2:
            actions.append({"kind":"bid","asset":contract.asset})
    for region, need in sorted(contract.needs.items(),key=lambda item:(p.connections[item[0]]-item[1],item[0])):
        if p.connections[region]<need and not game.locked(region):
            actions.append({"kind":"place","region":region})
    return actions

def opportunistic_burn(game: Game, player: str, disruptive: bool = False) -> list[dict]:
    """Return one legal, target-complete burn action with deterministic priorities."""
    p=game.players[player]
    contract_assets={c.asset for c in p.contracts}
    eligible=p.assets & p.assets_at_previous_turn - contract_assets
    rivals=sorted((x for x in game.players if x!=player), key=lambda x:(len(game.players[x].assets),game.players[x].connections.total(),game.players[x].influence), reverse=True)
    leader=rivals[0] if rivals else None
    if ("APPARATCHIK" in p.assets_at_previous_turn and "APPARATCHIK" in p.assets
            and "APPARATCHIK" not in contract_assets and sum(len(x.assets) for x in game.players.values()) >= 4):
        return [{"kind":"burn", "asset":"APPARATCHIK"}]
    if "ARMS DEPOT" in eligible:
        seize=[a for a in ASSET if legal_bid_target(game,player,a) and ASSET[a].region and p.connections[ASSET[a].region]]
        if seize: return [{"kind":"burn","asset":"ARMS DEPOT","target_asset":max(seize,key=lambda a:(ASSET[a].upkeep,a))}]
    if "INDEPENDENT TRADE UNION" in eligible and len(p.hand)>=3:
        return [{"kind":"burn","asset":"INDEPENDENT TRADE UNION"}]
    if "INTELLIGENCE LIAISON" in eligible and len(game.op_deck)>=3:
        top=game.op_deck[-3:]; discard=next((c for c in top if c not in {"Shell Company","Plausible Deniability","Double Cross"}),top[0])
        return [{"kind":"burn","asset":"INTELLIGENCE LIAISON","discard":discard}]
    if disruptive and "SMUGGLING RING" in eligible:
        targets=[]
        for region in sorted(REGIONS,key=lambda r:max(game.players[x].connections[r] for x in rivals),reverse=True):
            victim=max(rivals,key=lambda x:game.players[x].connections[region])
            if game.players[victim].connections[region]: targets.append({"player":victim,"region":region})
            if len(targets)==2: break
        if len(targets)==2: return [{"kind":"burn","asset":"SMUGGLING RING","targets":targets}]
    if disruptive and "STATE-ALIGNED MILITIA" in eligible:
        locked=[r for r in REGIONS if game.locked(r) and sum(game.players[x].connections[r] for x in rivals)]
        if locked: return [{"kind":"burn","asset":"STATE-ALIGNED MILITIA","region":max(locked,key=lambda r:sum(game.players[x].connections[r] for x in rivals))}]
    if disruptive and "NON-ALIGNED BLOC" in eligible and sum(len(game.players[x].assets) for x in rivals)>=3:
        return [{"kind":"burn","asset":"NON-ALIGNED BLOC"}]
    if disruptive and "OFFSHORE FINANCE NETWORK" in eligible and leader:
        return [{"kind":"burn","asset":"OFFSHORE FINANCE NETWORK","player":leader}]
    if "OIL CONSORTIUM" in eligible and p.influence>=5:
        return [{"kind":"burn","asset":"OIL CONSORTIUM"}]
    return []

class SeatPolicies:
    """Lets a single game use a different policy for every seat."""
    def __init__(self, policies: dict[str, Policy]): self.policies = policies
    def choose_actions(self, game: Game, player: str): return self.policies[player].choose_actions(game, player)
    def bid(self, game: Game, bidder: str, defender: str, asset: str) -> int:
        return self.policies[bidder].bid(game, bidder, defender, asset)

class ContractRushBot:
    """Prioritizes its private contract and pays conservatively in bids."""
    def bid(self, game, bidder, defender, asset):
        return min(game.players[bidder].influence // 3, 2)
    def choose_actions(self, game, player):
        p=game.players[player]
        for contract in p.contracts:
            if game.contract_met(player, contract): return [{"kind":"declare", "c":contract}]
        # A public contract needs no declaration: meeting it now wins at this player's next turn.
        if any(game.contract_met(player,c) for c in game.public_contracts): return []
        choice=closest_contract(game,player)
        actions=goal_actions(game,player,choice[0]) if choice else []
        return (actions + opportunistic_burn(game, player))[:4]

class IncomeBot:
    """Builds in low-congestion regions and buys the cheapest legal asset."""
    def bid(self, game, bidder, defender, asset):
        return game.players[bidder].influence // 2
    def choose_actions(self, game, player):
        p=game.players[player]
        declarations=[{"kind":"declare","c":c} for c in p.contracts if game.contract_met(player,c)]
        if declarations: return declarations
        if any(game.contract_met(player,c) for c in game.public_contracts): return []
        choice=closest_contract(game,player)
        actions=goal_actions(game,player,choice[0]) if choice else []
        legal_assets=[a for a in game.pool if (ASSET[a].region is None or p.connections[ASSET[a].region]) and p.influence>=ASSET[a].upkeep]
        if not actions and legal_assets: actions.append({"kind":"acquire", "asset":min(legal_assets, key=lambda a:(ASSET[a].upkeep,a))})
        open_regions=[r for r in REGIONS if not game.locked(r)]
        open_regions.sort(key=lambda r:(game.total_connections(r), r))
        actions.extend({"kind":"place", "region":r} for r in open_regions[:2])
        # Contest an affordable, high-upkeep asset only after building the income base.
        targets=[a for a in ASSET if legal_bid_target(game, player, a) and p.influence>=ASSET[a].upkeep+2]
        if targets: actions.append({"kind":"bid", "asset":max(targets,key=lambda a:(ASSET[a].upkeep,a))})
        return (actions + opportunistic_burn(game, player))[:4]

class DisruptorBot:
    """Uses destructive Operations cards, otherwise blocks the leading player."""
    def bid(self, game, bidder, defender, asset):
        return game.players[bidder].influence if asset in game.players[defender].assets else 0
    def choose_actions(self, game, player):
        p=game.players[player]
        declarations=[{"kind":"declare","c":c} for c in p.contracts if game.contract_met(player,c)]
        if declarations: return declarations
        rivals=sorted((x for x in game.players if x!=player), key=lambda x:(len(game.players[x].assets),game.players[x].connections.total(),game.players[x].influence), reverse=True)
        target=rivals[0]
        if any(game.contract_met(player,c) for c in game.public_contracts): return []
        choice=closest_contract(game,player)
        actions=goal_actions(game,player,choice[0]) if choice else []
        if "Regime Change" in p.hand:
            regions=sorted(REGIONS, key=lambda r:game.players[target].connections[r], reverse=True)
            if game.players[target].connections[regions[0]]: actions.append({"kind":"play_op","card":"Regime Change","region":regions[0]})
        elif "Asset Seizure" in p.hand and game.players[target].connections.total():
            actions.append({"kind":"play_op","card":"Asset Seizure","player":target})
        elif "Sanctions" in p.hand:
            actions.append({"kind":"play_op","card":"Sanctions","player":target})
        elif p.influence: actions.append({"kind":"buy_op"})
        # Make a connection only where it does not immediately lock a region.
        choices=[r for r in REGIONS if not game.locked(r) and game.total_connections(r)<game.capacity-1]
        if choices: actions.append({"kind":"place","region":min(choices,key=game.total_connections)})
        target_assets=[a for a in game.players[target].assets if legal_bid_target(game, player, a)]
        if target_assets and p.influence>=2: actions.append({"kind":"bid","asset":max(target_assets,key=lambda a:(ASSET[a].upkeep,a))})
        return (actions + opportunistic_burn(game, player, disruptive=True))[:4]
