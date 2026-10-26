"""Unit tests — run with:  python -m unittest discover -s tests -v"""

import json
import tempfile
import unittest
from pathlib import Path

from chainpulse import (Node, NodeType, P2PNetwork, bfs_propagate, compare,
                        connected_components, critical_nodes, dfs_explore,
                        generate_network, load_network, save_network,
                        shortest_relay_path)


def small_net() -> P2PNetwork:
    """
        A ── B ── D ── F
        │    │
        C ───┘    E (light, hangs off D)

    D is an articulation point (removing it cuts F and E off).
    B is an articulation point too (removing it cuts D, E, F off).
    """
    net = P2PNetwork()
    for nid in "ABCDF":
        net.add_node(Node(nid))
    net.add_node(Node("E", NodeType.LIGHT, relays=False))
    net.add_peer("A", "B", 10)
    net.add_peer("A", "C", 20)
    net.add_peer("B", "C", 5)
    net.add_peer("B", "D", 30)
    net.add_peer("D", "F", 40)
    net.add_peer("D", "E", 15)
    return net


class TestGraph(unittest.TestCase):
    def test_counts(self):
        net = small_net()
        self.assertEqual(net.node_count, 6)
        self.assertEqual(net.edge_count, 6)
        self.assertEqual(net.degree("B"), 3)

    def test_undirected(self):
        net = small_net()
        self.assertIn("A", net.adj["B"])
        self.assertIn("B", net.adj["A"])

    def test_invalid_edges(self):
        net = small_net()
        with self.assertRaises(ValueError):
            net.add_peer("A", "A")
        with self.assertRaises(KeyError):
            net.add_peer("A", "Z")
        with self.assertRaises(ValueError):
            net.add_node(Node("A"))


class TestBFS(unittest.TestCase):
    def test_levels_are_shortest_hops(self):
        r = bfs_propagate(small_net(), "A")
        self.assertEqual(r.level, {"A": 0, "B": 1, "C": 1, "D": 2, "E": 3, "F": 3})
        self.assertEqual(r.waves, [["A"], ["B", "C"], ["D"], ["E", "F"]])

    def test_full_coverage(self):
        r = bfs_propagate(small_net(), "A")
        self.assertEqual(r.coverage, 100.0)
        self.assertEqual(r.unreached, [])

    def test_arrival_time(self):
        r = bfs_propagate(small_net(), "A")
        self.assertEqual(r.arrival_ms["F"], 10 + 30 + 40)

    def test_offline_node_blocks_propagation(self):
        net = small_net()
        net.set_online("D", False)
        r = bfs_propagate(net, "A")
        self.assertEqual(sorted(r.unreached), ["D", "E", "F"])

    def test_light_node_does_not_relay(self):
        net = P2PNetwork()
        net.add_node(Node("X"))
        net.add_node(Node("L", NodeType.LIGHT, relays=False))
        net.add_node(Node("Y"))
        net.add_peer("X", "L")
        net.add_peer("L", "Y")
        r = bfs_propagate(net, "X")
        self.assertEqual(r.unreached, ["Y"])

    def test_bad_source(self):
        with self.assertRaises(KeyError):
            bfs_propagate(small_net(), "Z")


class TestDFS(unittest.TestCase):
    def test_order(self):
        r = dfs_explore(small_net(), "A")
        self.assertEqual(r.order, ["A", "B", "C", "D", "E", "F"])

    def test_reaches_same_set_as_bfs(self):
        net = generate_network(60, 2, seed=7)
        self.assertEqual(set(bfs_propagate(net, "N00").order),
                         set(dfs_explore(net, "N00").order))

    def test_dfs_depth_at_least_bfs_depth(self):
        net = generate_network(60, 3, seed=1)
        self.assertGreaterEqual(dfs_explore(net, "N00").max_hops,
                                bfs_propagate(net, "N00").max_hops)


class TestAnalytics(unittest.TestCase):
    def test_shortest_path(self):
        self.assertEqual(shortest_relay_path(small_net(), "C", "F"), ["C", "B", "D", "F"])

    def test_partitions(self):
        net = small_net()
        self.assertEqual(len(connected_components(net)), 1)
        net.set_online("B", False)
        self.assertEqual(connected_components(net), [["A", "C"], ["D", "E", "F"]])

    def test_critical_nodes(self):
        self.assertEqual(critical_nodes(small_net()), ["B", "D"])

    def test_cycle_has_no_critical_nodes(self):
        net = P2PNetwork()
        for n in "PQRS":
            net.add_node(Node(n))
        for a, b in ["PQ", "QR", "RS", "SP"]:
            net.add_peer(a, b)
        self.assertEqual(critical_nodes(net), [])

    def test_compare(self):
        out = compare(small_net(), "A")
        self.assertEqual(out["bfs"]["reached"], out["dfs"]["reached"])


class TestIO(unittest.TestCase):
    def test_roundtrip(self):
        net = generate_network(15, seed=3)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "n.json"
            save_network(net, p)
            back = load_network(p)
            self.assertEqual(back.edge_count, net.edge_count)
            self.assertIn("nodes", json.loads(p.read_text()))

    def test_large_network_no_recursion_error(self):
        net = generate_network(5000, 1, seed=9, light_ratio=0)   # deep tree, all relays
        self.assertEqual(dfs_explore(net, "N00").coverage, 100.0)
        critical_nodes(net)


if __name__ == "__main__":
    unittest.main()
