"""
traversal.py — BFS and DFS algorithms applied to a P2P blockchain network.

BFS  -> models *gossip propagation*: a node that receives a transaction
        forwards it to all of its peers, so the transaction spreads in
        "waves" (hop 0, hop 1, hop 2 ...). That is exactly BFS level order.
DFS  -> models *deep exploration / crawling*: a network crawler follows one
        peer chain as far as possible before backtracking. DFS is also the
        basis for finding network partitions and single points of failure
        (articulation points).

All traversals are iterative (explicit queue / stack) so they never hit
Python's recursion limit on large networks.

Complexity of every traversal here: Time O(V + E), Space O(V).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .graph import P2PNetwork


# ----------------------------------------------------------------------
# Result containers
# ----------------------------------------------------------------------
@dataclass
class PropagationResult:
    algorithm: str
    source: str
    order: List[str] = field(default_factory=list)          # visit order
    level: Dict[str, int] = field(default_factory=dict)      # hop count
    parent: Dict[str, Optional[str]] = field(default_factory=dict)
    arrival_ms: Dict[str, float] = field(default_factory=dict)
    waves: List[List[str]] = field(default_factory=list)     # BFS frontier per hop
    unreached: List[str] = field(default_factory=list)
    total_nodes: int = 0

    @property
    def reached(self) -> int:
        return len(self.order)

    @property
    def coverage(self) -> float:
        return round(100 * self.reached / self.total_nodes, 2) if self.total_nodes else 0.0

    @property
    def max_hops(self) -> int:
        return max(self.level.values(), default=0)

    @property
    def full_propagation_ms(self) -> float:
        return round(max(self.arrival_ms.values(), default=0.0), 2)

    def path_to(self, target: str) -> List[str]:
        """Reconstruct the relay path source -> target from the parent map."""
        if target not in self.parent:
            return []
        path, cur = [], target
        while cur is not None:
            path.append(cur)
            cur = self.parent[cur]
        return path[::-1]

    def summary(self) -> dict:
        return {
            "algorithm": self.algorithm,
            "source": self.source,
            "reached": self.reached,
            "total_nodes": self.total_nodes,
            "coverage_pct": self.coverage,
            "max_hops": self.max_hops,
            "full_propagation_ms": self.full_propagation_ms,
            "unreached": self.unreached,
        }


# ----------------------------------------------------------------------
# BFS — transaction gossip propagation
# ----------------------------------------------------------------------
def bfs_propagate(net: P2PNetwork, source: str) -> PropagationResult:
    """
    Simulate a transaction broadcast from `source` using Breadth-First Search.

    Rules that make it realistic:
      * offline nodes cannot receive the transaction
      * light (SPV) nodes receive it but do not relay further
    """
    if source not in net.nodes:
        raise KeyError(f"Unknown source node {source}")
    if not net.is_active(source):
        raise ValueError(f"Source node {source} is offline")

    res = PropagationResult("BFS", source, total_nodes=net.node_count)
    visited: Set[str] = {source}
    queue = deque([source])

    res.level[source] = 0
    res.parent[source] = None
    res.arrival_ms[source] = 0.0

    while queue:
        node = queue.popleft()                      # FIFO -> level order
        res.order.append(node)
        lvl = res.level[node]
        if len(res.waves) <= lvl:
            res.waves.append([])
        res.waves[lvl].append(node)

        if not net.nodes[node].relays and node != source:
            continue                                # light client: no relay

        for peer in net.peers(node):
            if peer in visited or not net.is_active(peer):
                continue
            visited.add(peer)
            res.level[peer] = lvl + 1
            res.parent[peer] = node
            res.arrival_ms[peer] = res.arrival_ms[node] + net.adj[node][peer]
            queue.append(peer)

    res.unreached = sorted(set(net.nodes) - visited)
    return res


# ----------------------------------------------------------------------
# DFS — deep network exploration / crawling
# ----------------------------------------------------------------------
def dfs_explore(net: P2PNetwork, source: str) -> PropagationResult:
    """
    Explore the network depth-first from `source` (iterative, explicit stack).
    `level` here is the depth of a node in the DFS tree, not the shortest hop.
    """
    if source not in net.nodes:
        raise KeyError(f"Unknown source node {source}")
    if not net.is_active(source):
        raise ValueError(f"Source node {source} is offline")

    res = PropagationResult("DFS", source, total_nodes=net.node_count)
    visited: Set[str] = set()
    # stack holds (node, parent)
    stack: List[tuple] = [(source, None)]

    while stack:
        node, par = stack.pop()                     # LIFO -> go deep first
        if node in visited:
            continue
        visited.add(node)
        res.order.append(node)
        res.parent[node] = par
        if par is None:
            res.level[node], res.arrival_ms[node] = 0, 0.0
        else:
            res.level[node] = res.level[par] + 1
            res.arrival_ms[node] = res.arrival_ms[par] + net.adj[par][node]

        if not net.nodes[node].relays and node != source:
            continue

        # push in reverse sorted order so the smallest id is explored first
        for peer in sorted(net.adj[node], reverse=True):
            if peer not in visited and net.is_active(peer):
                stack.append((peer, node))

    res.unreached = sorted(set(net.nodes) - visited)
    return res


# ----------------------------------------------------------------------
# Network-health analytics built on BFS / DFS
# ----------------------------------------------------------------------
def shortest_relay_path(net: P2PNetwork, src: str, dst: str) -> List[str]:
    """Fewest-hop route between two nodes (BFS). Empty list if unreachable."""
    return bfs_propagate(net, src).path_to(dst)


def connected_components(net: P2PNetwork) -> List[List[str]]:
    """
    Find network partitions (islands of nodes that cannot talk to each other).
    A partitioned blockchain risks forks and double-spends. Uses repeated DFS.
    """
    seen: Set[str] = set()
    comps: List[List[str]] = []
    for start in sorted(net.nodes):
        if start in seen or not net.is_active(start):
            continue
        comp, stack = [], [start]
        seen.add(start)
        while stack:
            n = stack.pop()
            comp.append(n)
            for p in net.adj[n]:
                if p not in seen and net.is_active(p):
                    seen.add(p)
                    stack.append(p)
        comps.append(sorted(comp))
    return comps


def critical_nodes(net: P2PNetwork) -> List[str]:
    """
    Articulation points (Tarjan's DFS low-link algorithm, iterative).
    If one of these nodes goes offline or is eclipsed by an attacker, the
    network splits into partitions — a single point of failure.
    Time O(V + E).
    """
    disc: Dict[str, int] = {}
    low: Dict[str, int] = {}
    parent: Dict[str, Optional[str]] = {}
    aps: Set[str] = set()
    timer = 0

    for root in sorted(net.nodes):
        if root in disc or not net.is_active(root):
            continue
        parent[root] = None
        disc[root] = low[root] = timer
        timer += 1
        root_children = 0
        stack = [(root, iter(sorted(net.adj[root])))]

        while stack:
            node, it = stack[-1]
            advanced = False
            for peer in it:
                if not net.is_active(peer):
                    continue
                if peer not in disc:
                    parent[peer] = node
                    disc[peer] = low[peer] = timer
                    timer += 1
                    if node == root:
                        root_children += 1
                    stack.append((peer, iter(sorted(net.adj[peer]))))
                    advanced = True
                    break
                elif peer != parent[node]:
                    low[node] = min(low[node], disc[peer])
            if advanced:
                continue
            stack.pop()
            par = parent[node]
            if par is not None:
                low[par] = min(low[par], low[node])
                if parent[par] is not None and low[node] >= disc[par]:
                    aps.add(par)

        if root_children > 1:
            aps.add(root)

    return sorted(aps)


def compare(net: P2PNetwork, source: str) -> dict:
    """Side-by-side BFS vs DFS on the same source node."""
    b, d = bfs_propagate(net, source), dfs_explore(net, source)
    return {
        "source": source,
        "bfs": b.summary() | {"order": b.order},
        "dfs": d.summary() | {"order": d.order},
        "insight": (
            f"BFS reaches every node in {b.max_hops} hops (shortest gossip waves); "
            f"DFS builds a chain {d.max_hops} levels deep. Real blockchains gossip "
            f"with BFS-like flooding because it minimises the hops to every peer."
        ),
    }
