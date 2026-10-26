"""
cli.py — Command-line interface for ChainPulse.

Examples
  python -m chainpulse demo
  python -m chainpulse bfs --source N00 --nodes 30
  python -m chainpulse dfs --source N05
  python -m chainpulse compare --source N00
  python -m chainpulse health --offline N03 N07
  python -m chainpulse path N00 N19
  python -m chainpulse export network.json
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .generator import generate_network, load_network, sample_transaction, save_network
from .traversal import (bfs_propagate, compare, connected_components,
                        critical_nodes, dfs_explore, shortest_relay_path)

BOLD, DIM, CYAN, GREEN, RED, YEL, RESET = (
    "\033[1m", "\033[2m", "\033[36m", "\033[32m", "\033[31m", "\033[33m", "\033[0m")
if not sys.stdout.isatty():
    BOLD = DIM = CYAN = GREEN = RED = YEL = RESET = ""


def banner() -> None:
    print(f"{CYAN}{BOLD}ChainPulse v{__version__}{RESET} "
          f"{DIM}— P2P Blockchain Network Explorer (BFS/DFS){RESET}\n")


def build(args):
    net = load_network(args.file) if args.file else generate_network(args.nodes, args.outbound, args.seed)
    for n in getattr(args, "offline", None) or []:
        net.set_online(n, False)
    return net


def print_result(net, res) -> None:
    s = res.summary()
    print(f"{BOLD}{res.algorithm} from {res.source}{RESET}")
    print(f"  Reached      : {GREEN}{s['reached']}/{s['total_nodes']}{RESET} ({s['coverage_pct']}%)")
    print(f"  Max depth    : {s['max_hops']} hops")
    print(f"  Est. latency : {s['full_propagation_ms']} ms (to the last node)")
    if res.unreached:
        print(f"  Unreached    : {RED}{', '.join(res.unreached)}{RESET}")
    print(f"  Visit order  : {' → '.join(res.order)}")
    if res.algorithm == "BFS":
        print(f"\n{BOLD}  Gossip waves{RESET}")
        for i, wave in enumerate(res.waves):
            bar = "█" * len(wave)
            print(f"   hop {i:<2} {YEL}{bar:<12}{RESET} {', '.join(wave)}")
    print()


def cmd_demo(args):
    net = build(args)
    tx = sample_transaction(net, args.source)
    print(f"{BOLD}Network{RESET}   {net.stats()}")
    print(f"{BOLD}Tx{RESET}        {tx.tx_id}  ₹{tx.amount:,.2f}  {tx.sender} → {tx.receiver}\n")
    print_result(net, bfs_propagate(net, args.source))
    print_result(net, dfs_explore(net, args.source))
    cmd_health(args, net)


def cmd_bfs(args):
    net = build(args)
    res = bfs_propagate(net, args.source)
    print(json.dumps(res.summary() | {"waves": res.waves}, indent=2)) if args.json else print_result(net, res)


def cmd_dfs(args):
    net = build(args)
    res = dfs_explore(net, args.source)
    print(json.dumps(res.summary() | {"order": res.order}, indent=2)) if args.json else print_result(net, res)


def cmd_compare(args):
    net = build(args)
    out = compare(net, args.source)
    if args.json:
        print(json.dumps(out, indent=2))
        return
    b, d = out["bfs"], out["dfs"]
    print(f"{BOLD}{'Metric':<22}{'BFS':>10}{'DFS':>10}{RESET}")
    for k, label in [("reached", "Nodes reached"), ("max_hops", "Max depth (hops)"),
                     ("full_propagation_ms", "Last arrival (ms)")]:
        print(f"{label:<22}{b[k]:>10}{d[k]:>10}")
    print(f"\n{DIM}{out['insight']}{RESET}")


def cmd_health(args, net=None):
    net = net or build(args)
    comps = connected_components(net)
    aps = critical_nodes(net)
    print(f"{BOLD}Network health{RESET}")
    status = f"{GREEN}HEALTHY{RESET}" if len(comps) == 1 else f"{RED}PARTITIONED{RESET}"
    print(f"  Partitions     : {len(comps)}  [{status}]")
    for i, c in enumerate(comps):
        print(f"    #{i + 1} ({len(c)} nodes) {', '.join(c)}")
    print(f"  Critical nodes : {RED}{', '.join(aps) or 'none'}{RESET}")
    print(f"  {DIM}(an attacker who eclipses a critical node can split the network){RESET}")


def cmd_path(args):
    net = build(args)
    p = shortest_relay_path(net, args.src, args.dst)
    print(" → ".join(p) if p else f"{RED}No route{RESET}")


def cmd_export(args):
    net = build(args)
    save_network(net, args.out)
    print(f"Saved {net} to {args.out}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="chainpulse", description="P2P Blockchain Network Explorer")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, src=True):
        p.add_argument("--nodes", type=int, default=20)
        p.add_argument("--outbound", type=int, default=2)
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--file", help="load network from JSON")
        p.add_argument("--offline", nargs="*", help="node ids to take offline")
        if src:
            p.add_argument("--source", default="N00")
        p.add_argument("--json", action="store_true")

    for name, fn in [("demo", cmd_demo), ("bfs", cmd_bfs), ("dfs", cmd_dfs),
                     ("compare", cmd_compare), ("health", cmd_health)]:
        p = sub.add_parser(name)
        common(p)
        p.set_defaults(fn=fn)

    p = sub.add_parser("path"); common(p, False)
    p.add_argument("src"); p.add_argument("dst"); p.set_defaults(fn=cmd_path)
    p = sub.add_parser("export"); common(p, False)
    p.add_argument("out"); p.set_defaults(fn=cmd_export)

    args = ap.parse_args(argv)
    banner()
    try:
        args.fn(args)
    except (KeyError, ValueError) as e:
        print(f"{RED}Error:{RESET} {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
