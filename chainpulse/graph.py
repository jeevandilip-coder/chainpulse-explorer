"""
graph.py — Peer-to-peer blockchain network modelled as an undirected weighted graph.

Representation: adjacency list  (dict[node_id] -> dict[peer_id] -> latency_ms)
  * add node / add edge  : O(1)
  * neighbours of a node : O(deg(v))
  * memory               : O(V + E)
An adjacency list is chosen over an adjacency matrix because real P2P
networks are sparse (Bitcoin Core keeps ~8 outbound + up to 125 inbound
peers out of ~15k reachable nodes), so a V x V matrix would waste memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterator, List


class NodeType(str, Enum):
    FULL = "full"        # validates and relays every transaction
    MINER = "miner"      # full node that also produces blocks
    LIGHT = "light"      # SPV client, receives but rarely relays
    EXCHANGE = "exchange"  # high-value FinTech endpoint (wallet / exchange)


@dataclass
class Node:
    node_id: str
    node_type: NodeType = NodeType.FULL
    region: str = "IN"
    online: bool = True
    relays: bool = True          # light clients do not forward

    def to_dict(self) -> dict:
        return {
            "id": self.node_id,
            "type": self.node_type.value,
            "region": self.region,
            "online": self.online,
            "relays": self.relays,
        }


@dataclass
class Transaction:
    tx_id: str
    sender: str
    receiver: str
    amount: float
    origin_node: str
    fee: float = 0.0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class P2PNetwork:
    nodes: Dict[str, Node] = field(default_factory=dict)
    adj: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # ---------- construction ----------
    def add_node(self, node: Node) -> None:
        if node.node_id in self.nodes:
            raise ValueError(f"Node {node.node_id} already exists")
        self.nodes[node.node_id] = node
        self.adj[node.node_id] = {}

    def add_peer(self, a: str, b: str, latency_ms: float = 50.0) -> None:
        """Create a bidirectional peer connection (undirected edge)."""
        if a == b:
            raise ValueError("A node cannot peer with itself")
        for n in (a, b):
            if n not in self.nodes:
                raise KeyError(f"Unknown node {n}")
        if latency_ms <= 0:
            raise ValueError("Latency must be positive")
        self.adj[a][b] = latency_ms
        self.adj[b][a] = latency_ms

    def remove_peer(self, a: str, b: str) -> None:
        self.adj[a].pop(b, None)
        self.adj[b].pop(a, None)

    def set_online(self, node_id: str, online: bool) -> None:
        self.nodes[node_id].online = online

    # ---------- queries ----------
    def peers(self, node_id: str) -> Iterator[str]:
        """Neighbours, sorted for deterministic traversal order."""
        return iter(sorted(self.adj[node_id]))

    def is_active(self, node_id: str) -> bool:
        return self.nodes[node_id].online

    def degree(self, node_id: str) -> int:
        return len(self.adj[node_id])

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return sum(len(p) for p in self.adj.values()) // 2

    def edges(self) -> List[tuple]:
        seen, out = set(), []
        for a, ps in self.adj.items():
            for b, w in ps.items():
                key = tuple(sorted((a, b)))
                if key not in seen:
                    seen.add(key)
                    out.append((key[0], key[1], w))
        return out

    def stats(self) -> dict:
        degs = [self.degree(n) for n in self.nodes] or [0]
        return {
            "nodes": self.node_count,
            "edges": self.edge_count,
            "online": sum(n.online for n in self.nodes.values()),
            "avg_degree": round(sum(degs) / len(degs), 2),
            "max_degree": max(degs),
            "min_degree": min(degs),
        }

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [{"a": a, "b": b, "latency_ms": w} for a, b, w in self.edges()],
        }

    def __repr__(self) -> str:
        return f"P2PNetwork(nodes={self.node_count}, edges={self.edge_count})"
