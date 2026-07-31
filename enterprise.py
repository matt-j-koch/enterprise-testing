"""A deterministic, bot-friendly rules engine for *The Enterprise*.

The engine deliberately separates legality/state transitions from bot policy.
Policies return plain dictionaries, so simulations can be replayed from a seed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter
from random import Random
from typing import Any, Protocol

REGIONS = ("LATIN AMERICA", "EUROPE", "USSR", "AFRICA", "MIDEAST", "ASIA")
MAX_CONNECTIONS_PER_PLAYER = 8
LOCKDOWN = {
    "LATIN AMERICA": "influence", "MIDEAST": "influence",
    "AFRICA": "remove", "ASIA": "remove", "EUROPE": "discard", "USSR": "discard",
}

@dataclass(frozen=True)
class AssetSpec:
    title: str; region: str | None; upkeep: int; passive: str; burn: str

@dataclass(frozen=True)
class ContractSpec:
    asset: str; needs: dict[str, int]

@dataclass
class Player:
    name: str; influence: int = 0; connections: Counter = field(default_factory=Counter)
    assets: set[str] = field(default_factory=set); hand: list[str] = field(default_factory=list)
    contracts: list[ContractSpec] = field(default_factory=list); fulfilled: int = 0
    first_turn_done: bool = False; pending_contract: ContractSpec | None = None
    returned_this_turn: set[str] = field(default_factory=set)
    acquisitions_this_turn: int = 0; placements_this_turn: int = 0; removed_voluntarily_this_turn: bool = False
    bids_initiated_this_turn: int = 0; assets_at_previous_turn: set[str] = field(default_factory=set)
    original_contracts: list[ContractSpec] = field(default_factory=list)

class Policy(Protocol):
    def choose_actions(self, game: "Game", player: str) -> list[dict[str, Any]]: ...
    def bid(self, game: "Game", bidder: str, defender: str, asset: str) -> int: ...

ASSETS = [
    AssetSpec("CENTRAL AMERICAN GUERILLAS", "LATIN AMERICA",0,"","force_bid"),
    AssetSpec("CARTEL NETWORK", "LATIN AMERICA",1,"own_remove_income","region_cost"),
    AssetSpec("POPULAR FRONT", "LATIN AMERICA",3,"siphon_region","swap_connections"),
    AssetSpec("SMUGGLING RING", "AFRICA",0,"","remove_two_regions"),
    AssetSpec("PRIVATE SECURITY CONTRACTORS", "AFRICA",1,"block_burn","forced_lock"),
    AssetSpec("PARTY-IN-EXILE", "AFRICA",2,"locked_income","reorder_deck"),
    AssetSpec("MUJAHIDEEN", "MIDEAST",0,"","copy_burn"),
    AssetSpec("OIL CONSORTIUM", "MIDEAST",3,"oil_income","extra_turn"),
    AssetSpec("ROYAL ATTACHE", "MIDEAST",2,"peek_deck","tutor_op"),
    AssetSpec("ARMS DEALER", "EUROPE",0,"","play_opponent_op"),
    AssetSpec("OFFSHORE FINANCE NETWORK", "EUROPE",1,"bid_surcharge","block_bids"),
    AssetSpec("PARLIAMENTARY FACTION", "EUROPE",2,"tax_first_targeted_op","redraw_hands"),
    AssetSpec("APPARATCHIK", "USSR",0,"","assets_income"),
    AssetSpec("ARMS DEPOT", "USSR",1,"fewest_assets_income","seize_asset"),
    AssetSpec("INDEPENDENT TRADE UNION", "USSR",2,"op_purchase_income","hand_income"),
    AssetSpec("TRIAD LOGISTICS WEB", "ASIA",0,"","move_two"),
    AssetSpec("STATE-ALIGNED MILITIA", "ASIA",1,"lock_income","clear_locked"),
    AssetSpec("NON-ALIGNED BLOC", "ASIA",2,"majority_income","asset_tax"),
    AssetSpec("INTELLIGENCE LIAISON",None,2,"peek_hand","draw_two"),
    AssetSpec("MERCENARY AIRLIFT",None,2,"free_move","copy_unused_burn"),
    AssetSpec("PRESS SYNDICATE",None,2,"public_draw","remove_public_contract"),
]
ASSET = {a.title:a for a in ASSETS}
OP_COPIES = {"Asset Seizure":3,"Backroom Deal":3,"Compromise":2,"Congressional Inquiry":2,
 "Cover Story":3,"Cut Out":3,"Double Cross":4,"False Flag":1,"Internal Purge":3,
 "Plausible Deniability":5,"Regime Change":1,"Safe House":2,"Sanctions":2,"Shakedown":2,"Shell Company":4}
CONTRACT_ROWS = [
 ("CENTRAL AMERICAN GUERILLAS", {"LATIN AMERICA":2,"USSR":1,"MIDEAST":1}),
 ("CARTEL NETWORK", {"LATIN AMERICA":2,"EUROPE":1}), ("SMUGGLING RING", {"EUROPE":1,"USSR":1,"AFRICA":2}),
 ("PRIVATE SECURITY CONTRACTORS", {"AFRICA":2,"MIDEAST":1}), ("MUJAHIDEEN", {"AFRICA":1,"MIDEAST":2,"ASIA":1}),
 ("OIL CONSORTIUM", {"LATIN AMERICA":1,"MIDEAST":2}), ("ARMS DEALER", {"LATIN AMERICA":1,"EUROPE":2,"AFRICA":1}),
 ("OFFSHORE FINANCE NETWORK", {"EUROPE":2,"ASIA":1}), ("APPARATCHIK", {"EUROPE":1,"USSR":2,"AFRICA":1}),
 ("ARMS DEPOT", {"USSR":2,"AFRICA":1}), ("TRIAD LOGISTICS WEB", {"USSR":1,"MIDEAST":1,"ASIA":2}),
 ("STATE-ALIGNED MILITIA", {"LATIN AMERICA":1,"ASIA":2}), ("POPULAR FRONT", {"LATIN AMERICA":2,"MIDEAST":1}),
 ("PARTY-IN-EXILE", {"AFRICA":2,"ASIA":1}), ("ROYAL ATTACHE", {"EUROPE":1,"MIDEAST":2}),
 ("PARLIAMENTARY FACTION", {"EUROPE":2,"USSR":1}), ("INDEPENDENT TRADE UNION", {"LATIN AMERICA":1,"USSR":2}),
 ("NON-ALIGNED BLOC", {"AFRICA":1,"ASIA":2}),]
CONTRACTS = [ContractSpec(a,n) for a,n in CONTRACT_ROWS]

def contract_id(contract: ContractSpec) -> tuple[str,tuple[tuple[str,int],...]]:
    return contract.asset, tuple(sorted(contract.needs.items()))

class IllegalMove(ValueError): pass

class Game:
    def __init__(self, names: list[str], seed: int = 1, two_contracts: bool | None = None):
        if not 2 <= len(names) <= 6: raise ValueError("2-6 players required")
        self.rng, self.players = Random(seed), {n:Player(n) for n in names}
        self.order, self.turn_index, self.turn_no, self.winner = list(names), 0, 0, None
        self.victory_contract: ContractSpec|None = None; self.victory_was_public = False; self.contract_origin:dict[tuple[str,tuple[tuple[str,int],...]],str] = {}
        self.two_contracts = len(names)==2 if two_contracts is None else two_contracts
        self.capacity = len(names)+1; self.pool:set[str] = set(); self.public_contracts:list[ContractSpec] = []
        self.op_deck = [c for c,n in OP_COPIES.items() for _ in range(n)]; self.rng.shuffle(self.op_deck)
        self.discard:list[str] = []; self.protected:dict[tuple[str,str],int] = {}; self.congress: str|None = None
        self.forced_locks:dict[str,int] = {}; self.bid_protected:dict[str,int] = {}; self.sanctions:dict[str,int] = {}
        self.region_costs:dict[str,tuple[int,int]] = {}; self.bid_blocked:dict[str,int] = {}; self.extra_turn_for: str|None = None
        self.event_log:list[str] = []; self._setup()

    def _setup(self) -> None:
        # One random asset per geographic region plus one regionless asset, as specified.
        for region in REGIONS:
            self.pool.add(self.rng.choice([a.title for a in ASSETS if a.region==region]))
        self.pool.add(self.rng.choice([a.title for a in ASSETS if a.region is None]))
        for _ in range(3):
            iterable = self.order if _ != 1 else list(reversed(self.order))
            for n in iterable:
                # Setup may fill a region, but may never place past capacity or trigger effects.
                open_regions=[r for r in REGIONS if self.total_connections(r)<self.capacity]
                self._place(n, self.rng.choice(open_regions), free=True, trigger=False)
        for n in reversed(self.order):
            p=self.players[n]; eligible=[a for a in self.pool if ASSET[a].region is None or p.connections[ASSET[a].region]]
            if eligible: self._take_asset(n, self.rng.choice(eligible), free=True)
            else:
                open_regions=[r for r in REGIONS if self.total_connections(r)<self.capacity]
                self._place(n, self.rng.choice(open_regions), free=True, trigger=False)
        available=[c for c in CONTRACTS if c.asset in self.pool or any(c.asset in p.assets for p in self.players.values())]
        self.rng.shuffle(available); deal=2 if self.two_contracts else 1
        for n in self.order:
            self.players[n].contracts=available[:deal]; self.players[n].original_contracts=list(available[:deal])
            for contract in available[:deal]: self.contract_origin[contract_id(contract)]=n
            del available[:deal]

    def current(self) -> str: return self.order[self.turn_index]
    def locked(self, region: str) -> bool: return self.congress==region or region in self.forced_locks or self.total_connections(region)>=self.capacity
    def total_connections(self, region: str) -> int: return sum(p.connections[region] for p in self.players.values())
    def _require_turn(self,n:str) -> Player:
        if n!=self.current(): raise IllegalMove("not this player's turn")
        return self.players[n]
    def _place(self,n:str,region:str,free:bool=False,trigger:bool=True) -> None:
        p=self.players[n]
        if region not in REGIONS or self.locked(region): raise IllegalMove("region is locked")
        if not free and p.removed_voluntarily_this_turn: raise IllegalMove("cannot place after voluntarily removing a connection")
        if not free and p.placements_this_turn: raise IllegalMove("only one connection may be placed per turn")
        if p.connections.total() >= MAX_CONNECTIONS_PER_PLAYER: raise IllegalMove("player connection limit reached")
        cost=0 if free or not p.connections.total() else 1+self.region_costs.get(region,(0,0))[0]
        if p.influence<cost: raise IllegalMove("need influence for connection")
        p.influence-=cost
        p.connections[region]+=1
        if not free: p.placements_this_turn+=1
        if trigger and self.total_connections(region)==self.capacity: self._trigger_lockdown(n,region)
    def place(self,n:str,region:str) -> None: self._place(self._require_turn(n).name,region)
    def remove(self,n:str,region:str,amount:int=1,voluntary:bool=True) -> None:
        p=self._require_turn(n) if voluntary else self.players[n]
        if p.connections[region]<amount: raise IllegalMove("not enough connections")
        p.connections[region]-=amount
        if voluntary:
            p.removed_voluntarily_this_turn=True
            p.influence+=amount
            for owner in self.players.values():
                if "CARTEL NETWORK" in owner.assets: owner.influence+=amount
    def _trigger_lockdown(self,trigger:str,region:str) -> None:
        for p in self.players.values():
            if "STATE-ALIGNED MILITIA" in p.assets: p.influence+=2
        effect=LOCKDOWN[region]
        if effect=="influence":
            for n,p in self.players.items():
                if n!=trigger: p.influence=max(0,p.influence-2)
        elif effect=="remove":
            for n,p in self.players.items():
                if n!=trigger and p.connections.total(): self._remove_any(n)
        else:
            for n,p in self.players.items():
                if n!=trigger and p.hand: self.discard.append(p.hand.pop(self.rng.randrange(len(p.hand))))
    def _remove_any(self,n:str) -> None:
        p=self.players[n]; choices=[r for r in REGIONS if p.connections[r]]
        if choices: p.connections[self.rng.choice(choices)]-=1
    def _take_asset(self,n:str,asset:str,free:bool=False) -> None:
        p=self.players[n]; spec=ASSET[asset]
        if asset not in self.pool or asset in p.returned_this_turn: raise IllegalMove("asset unavailable")
        if not free and p.acquisitions_this_turn: raise IllegalMove("only one asset may be acquired per turn")
        if spec.region and not p.connections[spec.region]: raise IllegalMove("missing regional connection")
        if not free and p.influence<spec.upkeep: raise IllegalMove("cannot pay asset cost")
        if not free: p.influence-=spec.upkeep
        self.pool.remove(asset); p.assets.add(asset)
        if not free: p.acquisitions_this_turn+=1
    def acquire(self,n:str,asset:str) -> None: self._take_asset(self._require_turn(n).name,asset)
    def _return_asset(self,owner:str,asset:str) -> None:
        self.players[owner].assets.remove(asset); self.players[owner].returned_this_turn.add(asset); self.pool.add(asset)
    def buy_op(self,n:str) -> None:
        p=self._require_turn(n)
        if not self.op_deck: self.op_deck,self.discard=self.discard,[]; self.rng.shuffle(self.op_deck)
        if not self.op_deck or p.influence<1: raise IllegalMove("cannot buy operation")
        p.influence-=1; p.hand.append(self.op_deck.pop())
        for owner in self.players.values():
            if owner.name!=n and "INDEPENDENT TRADE UNION" in owner.assets: owner.influence+=1
    def bid(self,n:str,asset:str,policy:Policy,backroom:bool=False,cut_out:bool=False) -> None:
        attacker=self._require_turn(n); owners=[x for x,p in self.players.items() if asset in p.assets]
        if not owners: raise IllegalMove("asset is not owned")
        if attacker.bids_initiated_this_turn: raise IllegalMove("only one bidding phase may be initiated per turn")
        defender=owners[0]
        if not self.players[defender].first_turn_done or asset in self.bid_protected or n in self.bid_blocked: raise IllegalMove("asset cannot be bid on")
        a=max(0,min(attacker.influence,policy.bid(self,n,defender,asset))); d=max(0,min(self.players[defender].influence,policy.bid(self,defender,n,asset)))
        attacker.influence-=a; self.players[defender].influence-=d
        winner=n if a>d else defender
        if winner==n and "OFFSHORE FINANCE NETWORK" in self.players[defender].assets:
            if attacker.influence<1: winner="" # asset returns below
            else: attacker.influence-=1
        if winner==n:
            self.players[defender].assets.remove(asset)
            if backroom:
                if attacker.influence<1: raise IllegalMove("backroom requires 1 influence")
                attacker.influence-=1; self.pool.add(asset)
            else: attacker.assets.add(asset)
        elif winner=="": self.players[defender].assets.remove(asset); self.pool.add(asset)
        elif cut_out: attacker.influence+=min(2,a)
        self.bid_protected[asset]=self.turn_no+1
        attacker.bids_initiated_this_turn+=1
    def contract_met(self,n:str,c:ContractSpec) -> bool:
        p=self.players[n]; return c.asset in p.assets and all(p.connections[r]>=x for r,x in c.needs.items())
    def declare(self,n:str,c:ContractSpec) -> None:
        p=self._require_turn(n)
        if c not in p.contracts or not self.contract_met(n,c): raise IllegalMove("contract not met")
        p.pending_contract=c; p.contracts.remove(c); self.public_contracts.append(c)
        bonus=max(0,4-len(self.public_contracts)); p.influence+=bonus
        for x in self.players.values():
            if "PRESS SYNDICATE" in x.assets: self._draw(x)
    def _draw(self,p:Player) -> None:
        if self.op_deck: p.hand.append(self.op_deck.pop())
    def play_op(self,n:str,card:str,**target:Any) -> None:
        p=self._require_turn(n)
        if card not in p.hand: raise IllegalMove("card not in hand")
        p.hand.remove(card); self.discard.append(card)
        other=target.get("player"); region=target.get("region")
        if card=="Shell Company": p.influence+=2
        elif card=="Asset Seizure": self._remove_any(other) if other else None
        elif card=="Internal Purge" and other and self.players[other].hand: self.discard.append(self.players[other].hand.pop(self.rng.randrange(len(self.players[other].hand))))
        elif card=="Regime Change" and region:
            for x in self.players: self.players[x].connections[region]=0
            for x in list(self.players):
                for a in list(self.players[x].assets):
                    if ASSET[a].region==region: self._return_asset(x,a)
        elif card=="Sanctions" and other: self.sanctions[other]=self.turn_no+1
        elif card=="Shakedown" and other:
            victim=self.players[other]
            if victim.influence>=3: victim.influence-=3; p.influence+=3
            else: self._remove_any(other); self._remove_any(other)
        elif card=="Congressional Inquiry" and region: self.congress=region
        elif card=="Cover Story" and region: self.protected[(n,region)]=self.turn_no+1
        # Reaction/counterspell timing is exposed to a policy-driven caller; it does not alter turn state here.
    def burn(self,n:str,asset:str,**target:Any) -> None:
        """Burn an eligible Asset. `target` carries the choices demanded by its effect."""
        p=self._require_turn(n)
        if asset not in p.assets or asset not in p.assets_at_previous_turn or asset in p.returned_this_turn:
            raise IllegalMove("asset was not controlled on your previous turn")
        effect=ASSET[asset].burn; other=target.get("player"); region=target.get("region")
        if effect=="region_cost":
            if region not in REGIONS: raise IllegalMove("choose a region")
            self.region_costs[region]=(2,self.turn_no+len(self.order))
        elif effect=="remove_two_regions":
            choices=target.get("targets",[])
            if len(choices)!=2: raise IllegalMove("choose two connection targets")
            for choice in choices:
                victim,where=choice.get("player"),choice.get("region")
                if victim not in self.players or where not in REGIONS or not self.players[victim].connections[where]: raise IllegalMove("invalid connection target")
                self.players[victim].connections[where]-=1
        elif effect=="forced_lock":
            if region not in REGIONS: raise IllegalMove("choose a region")
            self.forced_locks[region]=self.turn_no+len(self.order); self._trigger_lockdown(n,region)
        elif effect=="extra_turn": self.extra_turn_for=n
        elif effect=="tutor_op":
            card=target.get("card")
            if card not in self.op_deck: raise IllegalMove("chosen card is not in deck")
            self.op_deck.remove(card); p.hand.append(card); self.rng.shuffle(self.op_deck)
        elif effect=="block_bids":
            if other not in self.players: raise IllegalMove("choose an opponent")
            self.bid_blocked[other]=self.turn_no+len(self.order)
        elif effect=="assets_income": p.influence+=sum(len(x.assets) for x in self.players.values())
        elif effect=="seize_asset":
            chosen=target.get("target_asset"); owner=next((x for x,q in self.players.items() if chosen in q.assets),None)
            if not owner or owner==n or not ASSET[chosen].region or not p.connections[ASSET[chosen].region]: raise IllegalMove("cannot seize that asset")
            self.players[owner].assets.remove(chosen); p.assets.add(chosen)
        elif effect=="hand_income": p.influence+=len(p.hand); self.discard.extend(p.hand); p.hand=[]
        elif effect=="move_two":
            moves=target.get("moves",[])
            if len(moves)!=2: raise IllegalMove("choose two moves")
            for move in moves:
                start,end=move.get("from"),move.get("to")
                if start not in REGIONS or end not in REGIONS or start==end or not p.connections[start] or self.locked(end): raise IllegalMove("invalid move")
                p.connections[start]-=1; p.connections[end]+=1
        elif effect=="clear_locked":
            if region not in REGIONS or not self.locked(region): raise IllegalMove("choose a locked region")
            for x,q in self.players.items():
                if x!=n: q.connections[region]=0
        elif effect=="asset_tax":
            for x,q in self.players.items():
                if x!=n: q.influence=max(0,q.influence-len(q.assets))
        elif effect=="draw_two":
            if len(self.op_deck)<3: raise IllegalMove("not enough Operations cards")
            top=[self.op_deck.pop() for _ in range(3)]; discard_card=target.get("discard")
            if discard_card not in top: raise IllegalMove("choose one of the top three to discard")
            top.remove(discard_card); p.hand.extend(top); self.discard.append(discard_card)
        elif effect=="copy_unused_burn":
            chosen=target.get("asset")
            if chosen not in self.pool or p.influence<ASSET[chosen].upkeep: raise IllegalMove("choose an unused asset you can fund")
            p.influence-=ASSET[chosen].upkeep; self.event_log.append(f"{n} copied {chosen}'s burn")
        elif effect=="remove_public_contract":
            index=target.get("contract_index")
            if len(self.public_contracts)<=1 or not isinstance(index,int) or not 0<=index<len(self.public_contracts): raise IllegalMove("cannot remove that public contract")
            self.public_contracts.pop(index)
        else:
            # The remaining burns require a multi-party/card-resolution policy. Keep the action auditable.
            self.event_log.append(f"{n} burned {asset}: {effect}; target={target}")
        self._return_asset(n,asset)
    def begin_turn(self) -> None:
        n=self.current(); p=self.players[n]; self.turn_no+=1; p.returned_this_turn.clear(); p.acquisitions_this_turn=0; p.placements_this_turn=0; p.removed_voluntarily_this_turn=False; p.bids_initiated_this_turn=0
        self.forced_locks={r:expiry for r,expiry in self.forced_locks.items() if expiry>self.turn_no}
        self.region_costs={r:rule for r,rule in self.region_costs.items() if rule[1]>self.turn_no}
        self.bid_blocked={x:expiry for x,expiry in self.bid_blocked.items() if expiry>self.turn_no}
        if p.pending_contract and self.contract_met(n,p.pending_contract):
            completed=p.pending_contract; p.fulfilled+=1; p.pending_contract=None
            if p.fulfilled >= (2 if self.two_contracts else 1):
                self.winner=n; self.victory_contract=completed; self.victory_was_public=False; return
        # Public contracts are checked at turn start and may be fulfilled by anyone.
        public=next((c for c in self.public_contracts if self.contract_met(n,c)),None)
        if public:
            self.winner=n; self.victory_contract=public; self.victory_was_public=True; return
        # Turn order from the rules: Connections pay out before Asset maintenance.
        for r,count in p.connections.items():
            if count and (not self.locked(r) or "PARTY-IN-EXILE" in p.assets): p.influence+=count
        if "ARMS DEPOT" in p.assets and len(p.assets)==min(len(x.assets) for x in self.players.values()): p.influence+=1
        if "NON-ALIGNED BLOC" in p.assets:
            p.influence+=sum(p.connections[r]==max(x.connections[r] for x in self.players.values()) and p.connections[r]>0 for r in REGIONS)
        for owner in self.players.values():
            if owner.name!=n and "OIL CONSORTIUM" in owner.assets and p.connections.total()>owner.connections.total(): owner.influence+=1
        for asset in list(p.assets):
            spec=ASSET[asset]; cost=spec.upkeep+(1 if self.sanctions.get(n)==self.turn_no else 0)
            if spec.region and not p.connections[spec.region]: self._return_asset(n,asset)
            elif p.influence>=cost: p.influence-=cost
            else: self._return_asset(n,asset)
    def end_turn(self) -> None:
        p=self.players[self.current()]; p.first_turn_done=True; p.assets_at_previous_turn=set(p.assets)
        if self.extra_turn_for==self.current(): self.extra_turn_for=None; return
        self.turn_index=(self.turn_index+1)%len(self.order)
    def run(self, policy:Policy, max_turns:int=500) -> str|None:
        for _ in range(max_turns):
            self.begin_turn()
            if self.winner: return self.winner
            n=self.current()
            for action in policy.choose_actions(self,n):
                try:
                    kind=action.pop("kind")
                    if kind=="place": self.place(n,**action)
                    elif kind=="remove": self.remove(n,**action)
                    elif kind=="acquire": self.acquire(n,**action)
                    elif kind=="buy_op": self.buy_op(n)
                    elif kind=="bid": self.bid(n,policy=policy,**action)
                    elif kind=="play_op": self.play_op(n,**action)
                    elif kind=="burn": self.burn(n,**action)
                    elif kind=="declare": self.declare(n,**action)
                except IllegalMove: pass
            self.end_turn()
        return None

class GreedyBot:
    """A baseline policy: pursues its contract and handles no hidden information."""
    def bid(self,game:Game,bidder:str,defender:str,asset:str)->int: return game.players[bidder].influence//2
    def choose_actions(self,game:Game,player:str)->list[dict[str,Any]]:
        p=game.players[player]; actions=[]
        for c in p.contracts:
            if game.contract_met(player,c): return [{"kind":"declare","c":c}]
            if c.asset in game.pool and ASSET[c.asset].region in (None,*[r for r in REGIONS if p.connections[r]]): actions.append({"kind":"acquire","asset":c.asset})
            for r,need in c.needs.items():
                if p.connections[r]<need: actions.append({"kind":"place","region":r})
        return actions[:3]

if __name__ == "__main__":
    game=Game(["Bot A","Bot B","Bot C"],seed=7)
    print("winner:",game.run(GreedyBot()), "turns:",game.turn_no)
