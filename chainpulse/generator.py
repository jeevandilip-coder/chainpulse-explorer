"""
generator.py — Builds realistic sample P2P networks (seeded, reproducible).

Topology: each new node opens `outbound` connections to random existing
nodes (similar to how Bitcoin/Ethereum clients pick peers), which yields a
sparse, mostly-connected graph with a few hubs.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from .graph import Node, NodeType, P2PNetwork, Transaction

REGIONS = ["IN", "SG", "US", "DE", "JP", "BR", "AE", "UK"]


def generate_network(n: int = 20, outbound: int = 2, seed: int = 42,
                     light_ratio: float = 0.15) -> P2PNetwork:
    if n < 2:
        raise ValueError("Need at least 2 nodes")
    rng = random.Random(seed)
    net = P2PNetwork()

    for i in range(n):
        nid = f"N{i:02d}"
        roll = rng.random()
        if i == 0:
            ntype = NodeType.MINER
        elif roll < light_ratio:
            ntype = NodeType.LIGHT
        elif roll < light_ratio + 0.15:
            ntype = NodeType.MINER
        elif roll < light_ratio + 0.25:
            ntype = NodeType.EXCHANGE
        else:
            ntype = NodeType.FULL
        net.add_node(Node(nid, ntype, rng.choice(REGIONS),
                          relays=ntype != NodeType.LIGHT))

        # connect to earlier nodes (guarantees one connected component)
        if i > 0:
            k = min(outbound, i)
            for peer in rng.sample(range(i), k):
                net.add_peer(nid, f"N{peer:02d}", round(rng.uniform(15, 180), 1))
    return net


def sample_transaction(net: P2PNetwork, origin: str = "N00") -> Transaction:
    return Transaction(
        tx_id="0x7f3a9c21e4b8",
        sender="wallet:shaju",
        receiver="wallet:merchant",
        amount=2500.0,
        fee=1.25,
        origin_node=origin,
    )


def load_network(path: str | Path) -> P2PNetwork:
    """Load a network from JSON: {"nodes":[{id,type,...}], "edges":[{a,b,latency_ms}]}"""
    data = json.loads(Path(path).read_text())
    net = P2PNetwork()
    for nd in data["nodes"]:
        t = NodeType(nd.get("type", "full"))
        net.add_node(Node(nd["id"], t, nd.get("region", "IN"),
                          nd.get("online", True), nd.get("relays", t != NodeType.LIGHT)))
    for e in data["edges"]:
        net.add_peer(e["a"], e["b"], e.get("latency_ms", 50.0))
    return net


def save_network(net: P2PNetwork, path: str | Path) -> None:
    Path(path).write_text(json.dumps(net.to_dict(), indent=2))
