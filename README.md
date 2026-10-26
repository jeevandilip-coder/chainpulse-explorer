# ChainPulse — Peer-to-Peer Blockchain Network Explorer

> **Micro Project 12** · Industry focus: **FinTech** · Integrated CO: **CO4**
> *Model blockchain nodes as a graph. Implement BFS / DFS traversal to explore how transactions propagate across the network.*

ChainPulse models a blockchain's peer-to-peer network as an **undirected weighted graph** and uses
**Breadth-First Search** and **Depth-First Search** to show how a single transaction travels from the
wallet that created it to every node in the network. On top of the core traversal it adds two
network-security analytics that matter in FinTech: **partition detection** and **critical-node
(articulation point) detection**.

| Deliverable | Path |
|---|---|
| Graph model (adjacency list) | `chainpulse/graph.py` |
| BFS, DFS, path, partitions, critical nodes | `chainpulse/traversal.py` |
| Seeded network generator + JSON I/O | `chainpulse/generator.py` |
| Command-line explorer | `chainpulse/cli.py` |
| Unit tests (19 cases, stdlib `unittest`) | `tests/test_chainpulse.py` |
| Interactive web explorer (single HTML file) | `web/index.html` |
| Sample network | `docs/sample_network.json` |

No third-party packages are required. Python 3.9+.

---

## 1. Problem statement

When a user sends money on a blockchain, the transaction is created on **one** node. Before a
miner can put it in a block, it must reach the rest of the network. There is no central server;
every node only knows its own peers. The questions this project answers:

1. In what order, and in how many hops, does the transaction reach every node?
2. How long does full propagation take, given per-link latency?
3. Is the network fully connected, or split into islands (partitions)?
4. Which single nodes, if taken down or eclipsed by an attacker, would split the network?

## 2. Data structure design

### Graph representation

```
adj = {
  "N00": {"N01": 42.5, "N03": 118.0},   # peer -> latency in ms
  "N01": {"N00": 42.5, "N02": 77.1},
  ...
}
```

* **Vertices** = blockchain nodes (`Node`: id, type, region, online, relays)
* **Edges** = peer connections, undirected, weighted by network latency (ms)
* **Adjacency list** (dict of dicts) instead of an adjacency matrix, because P2P networks are
  sparse: each node keeps a handful of peers out of thousands of nodes. Memory is O(V + E)
  instead of O(V²), and edge lookup stays O(1).

### Node types

| Type | Behaviour in propagation |
|---|---|
| `full` | validates and relays every transaction |
| `miner` | full node that also produces blocks |
| `exchange` | high-value FinTech endpoint (wallet / exchange) |
| `light` | SPV client: receives the transaction but **does not relay** it |

Offline nodes can neither receive nor relay.

## 3. Algorithms

### BFS — transaction gossip (`bfs_propagate`)

A node that receives a new transaction forwards it to all of its peers, who forward it to
theirs. The transaction spreads in waves: hop 0, hop 1, hop 2… That is exactly BFS level order,
implemented with a **queue (FIFO)**.

```
queue ← [source]; visited ← {source}
while queue not empty:
    node ← queue.dequeue()
    record node (level, arrival time, parent)
    if node is a light client: continue          # receives, does not relay
    for peer in neighbours(node):
        if peer not visited and peer online:
            visited.add(peer); parent[peer] ← node
            level[peer] ← level[node] + 1
            arrival[peer] ← arrival[node] + latency(node, peer)
            queue.enqueue(peer)
```

Output: visit order, hop level per node, gossip waves, relay tree (parent map), estimated
arrival time per node, coverage %, and unreached nodes.

> **Analogy:** a WhatsApp forward. You send it to your 5 contacts, each of them forwards to their
> contacts, and the message spreads in rounds. BFS counts those rounds.

### DFS — deep network crawl (`dfs_explore`)

A network crawler follows one peer chain as far as it goes before backtracking, using a
**stack (LIFO)**. The implementation is iterative (explicit stack), so it handles 5,000+ node
chains without hitting Python's recursion limit.

> **Analogy:** exploring a maze by always taking the first unexplored corridor and only turning
> back at a dead end.

### Analytics built on BFS / DFS

| Function | Technique | Why it matters in FinTech |
|---|---|---|
| `shortest_relay_path(a, b)` | BFS parent map | fewest-hop route between two nodes |
| `connected_components()` | repeated DFS | a partitioned network can fork and allow double-spends |
| `critical_nodes()` | Tarjan's DFS low-link (articulation points) | nodes whose loss splits the network; prime targets for eclipse attacks |
| `compare(source)` | BFS vs DFS side by side | shows why real gossip protocols behave like BFS |

## 4. Complexity analysis

| Operation | Time | Space |
|---|---|---|
| `add_node`, `add_peer`, `remove_peer` | O(1) | O(1) |
| `peers(v)` (sorted for determinism) | O(d log d) | O(d) |
| `bfs_propagate` | O(V + E) | O(V) |
| `dfs_explore` | O(V + E) | O(V) |
| `shortest_relay_path` | O(V + E) | O(V) |
| `connected_components` | O(V + E) | O(V) |
| `critical_nodes` (Tarjan) | O(V + E) | O(V) |

V = nodes, E = peer links, d = degree of a node.

## 5. Running it

```bash
# full walkthrough: network stats, BFS waves, DFS order, health check
python3 -m chainpulse demo

# individual commands
python3 -m chainpulse bfs --source N00 --nodes 30
python3 -m chainpulse dfs --source N05
python3 -m chainpulse compare --source N00
python3 -m chainpulse health --offline N01 N02      # simulate nodes going down
python3 -m chainpulse path N00 N19
python3 -m chainpulse export my_network.json --nodes 40
python3 -m chainpulse bfs --file docs/sample_network.json --json

# tests
python3 -m unittest discover -s tests -v
```

Open `web/index.html` in any browser for the visual explorer: pick BFS or DFS, choose the
source node, press **Play** or **Step**, and watch the queue / stack, gossip waves and relay tree
update live. Click a node to take it offline and see the network partition.

### Sample output (`python3 -m chainpulse demo`)

```
Network   {'nodes': 20, 'edges': 37, 'online': 20, 'avg_degree': 3.7, 'max_degree': 9, 'min_degree': 2}
Tx        0x7f3a9c21e4b8  ₹2,500.00  wallet:shaju → wallet:merchant

BFS from N00
  Reached      : 20/20 (100.0%)
  Max depth    : 3 hops
  Est. latency : 390.5 ms (to the last node)

  Gossip waves
   hop 0  █            N00
   hop 1  ██████       N01, N02, N03, N04, N07, N13
   hop 2  ███████      N05, N09, N17, N08, N14, N19, N15
   hop 3  ██████       N06, N10, N16, N11, N18, N12

DFS from N00
  Reached      : 20/20 (100.0%)
  Max depth    : 10 hops
  Est. latency : 896.8 ms (to the last node)
```

**Observation:** on the same 20-node network BFS reaches everyone in 3 hops, while the DFS tree is
10 levels deep. Gossip protocols in Bitcoin and Ethereum flood transactions in BFS-like waves for
exactly this reason.

## 6. Testing

19 unit tests cover graph construction and validation, BFS levels and arrival times, offline
and light-client behaviour, DFS order, BFS/DFS reaching the same node set, shortest paths,
partitions, articulation points (including a cycle with none), JSON round-trip, and a
5,000-node chain to prove the iterative DFS never overflows the call stack.

```
Ran 19 tests in 0.07s
OK
```

## 7. Limitations and future work

* Arrival time follows the BFS tree (fewest hops). True earliest-arrival time would use
  Dijkstra's algorithm on the latency weights.
* Real gossip uses inventory announcements (`inv` / `getdata`) rather than pushing the full
  transaction; this model treats each relay as one step.
* Possible extensions: live data from a Bitcoin testnet node's `getpeerinfo`, block (not just
  transaction) propagation, and simulating an eclipse attack on a critical node.

## 8. Project structure

```
chainpulse/
├── chainpulse/
│   ├── __init__.py
│   ├── __main__.py      # python -m chainpulse
│   ├── cli.py
│   ├── generator.py
│   ├── graph.py
│   └── traversal.py
├── tests/
│   └── test_chainpulse.py
├── web/
│   └── index.html
├── docs/
│   └── sample_network.json
└── README.md
```

---
**Author:** Shajilin Benadict S (URK25DS3024) · B.Sc. Information Security and Digital Forensics, Karunya University
