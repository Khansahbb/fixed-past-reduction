"""Three-key exhaustive comparison (reviewer R1-W3) with a counter for the scenario
Theorem 1's forward proof turns on: a winning play under the final-deadline policy whose
realised prefix has length >= 2 and contains a defending key with a legal quiet successor
that is in B but NOT on the prefix.

Sub-family (to keep Python runtime sane): per key 2 owners x 8 quiet subsets x 4 exit
options ({}, {W0}, {W1}, {D}) = 64 nonterminal configs + 3 terminals = 67; 67^3 arenas.
Rules (2,3,2,3); past counts in {0,1,2}^3; both roots... all 3 roots; clocks 0..3.
"""
import json, sys, time
from itertools import product, combinations
from model import *

def configs3():
    cfgs = []
    qs = []
    for k in range(4):
        qs += [tuple(c) for c in combinations(range(3), k)]
    for owner in (0, 1):
        for q in qs:
            for ex in [(), (WIN0,), (WIN1,), (DRAW,)]:
                cfgs.append(Node(None, owner, q, ex))
    for o in TERMINAL_OUTCOMES:
        cfgs.append(Node(o))
    return cfgs

def scenario_hit(arena, rules, P, D, A, B, q0, h0, counts_g):
    """DFS over all opponent replies along the final-deadline policy from (q0,h0).
    Returns True if some reachable defending key on a prefix of length>=2 has a quiet
    successor in B that is off the prefix."""
    nodes = arena.nodes
    stack = [(q0, h0, (q0,))]
    while stack:
        q, h, prefix = stack.pop()
        nd = nodes[q]
        if nd.terminal is not None or D[q] < 0 or h > D[q]:
            continue
        if nd.owner == P:
            # choose an action winning at deadline D[q]: prefer quiet edges (longer prefixes)
            chosen = None
            for q2 in nd.quiet:
                if nodes[q2].terminal is not None:
                    if nodes[q2].terminal == P and D[q] <= rules.H - 1: chosen = ('t', q2)
                elif D[q2] - 1 >= D[q]:
                    chosen = ('q', q2); break
            if chosen is None:
                continue  # exit or terminal: play ends
            if chosen[0] == 'q':
                stack.append((chosen[1], h + 1, prefix + (chosen[1],)))
        else:
            if len(prefix) >= 2:
                for q2 in nd.quiet:
                    if counts_g[q2] == rules.r - 2 and q2 not in prefix:
                        return True
            for q2 in nd.quiet:
                if nodes[q2].terminal is None:
                    stack.append((q2, h + 1, prefix + (q2,)))
    return False

if __name__ == "__main__":
    rules = Rules(3, 5, 4, 6)
    cfgs = configs3()
    n_cfg = len(cfgs)
    stats = dict(rules=rules.__dict__, configs_per_key=n_cfg, arenas=n_cfg**3, past_cases=0, root_queries=0,
                 mismatch=0, wins=0, scenario_queries=0, max_rounds=0)
    t0 = time.time(); ai = 0
    counts_space = list(product(range(rules.a), repeat=3))
    for x in cfgs:
        for y in cfgs:
            for z in cfgs:
                arena = Arena((x, y, z)); ai += 1
                for counts in counts_space:
                    stats["past_cases"] += 1
                    A, B = masks(rules, counts)
                    Ds = {}
                    for P in (0, 1):
                        Ds[P], r = deadline_vector(arena, rules, P, A, B)
                        stats["max_rounds"] = max(stats["max_rounds"], r)
                    for q0 in range(3):
                        if arena.nodes[q0].terminal is not None: continue
                        for h0 in range(rules.H + 1):
                            stats["root_queries"] += 1
                            ve = explicit_value(arena, rules, q0, h0, counts)
                            w0 = h0 <= Ds[0][q0]; w1 = h0 <= Ds[1][q0]
                            vd = WIN0 if w0 else WIN1 if w1 else DRAW
                            if ve != vd:
                                stats["mismatch"] += 1
                                print("MISMATCH", [n.__dict__ for n in arena.nodes], counts, q0, h0, ve, vd)
                            if vd != DRAW:
                                stats["wins"] += 1
                                P = vd
                                if scenario_hit(arena, rules, P, Ds[P], A, B, q0, h0, counts):
                                    stats["scenario_queries"] += 1
                if ai % 20000 == 0:
                    print(ai, stats["root_queries"], stats["mismatch"], stats["scenario_queries"], f"{time.time()-t0:.0f}s", file=sys.stderr)
    stats["seconds"] = round(time.time() - t0)
    json.dump(stats, open("../results/threekey_r3.json", "w"), indent=1)
    print(json.dumps(stats, indent=1))
