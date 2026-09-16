"""Reproduce Table I of the manuscript with independent code, and red-team
Theorem 1 / Corollary 4 on the two-key exhaustive domain plus random arenas.

Outputs results/exhaustive.json and prints a summary. Any mismatch is dumped
in full so it can be inspected.
"""
import json, random, sys, time
from itertools import product
from model import *


def run_exhaustive(rules: Rules, tag: str):
    arenas = all_two_key_arenas()
    counts_space = list(product(range(rules.a), repeat=2))
    stats = dict(tag=tag, rules=rules.__dict__, arenas=len(arenas),
                 past_cases=len(arenas) * len(counts_space), root_queries=0,
                 mismatch_explicit_vs_deadline=0, mismatch_explicit_vs_clocklayer=0,
                 corollary7_alternating_cases=0, corollary7_mismatch=0,
                 corollary7_nonalternating_mismatch=0, max_rounds=0)
    mismatches = []
    t0 = time.time()
    for ai, arena in enumerate(arenas):
        alternating = all(
            nd.terminal is not None or all(
                arena.nodes[q2].terminal is not None or arena.nodes[q2].owner != nd.owner
                for q2 in nd.quiet)
            for nd in arena.nodes)
        for counts in counts_space:
            A, B = masks(rules, counts)
            for P in (0, 1):
                _, rounds = deadline_vector(arena, rules, P, A, B)
                stats["max_rounds"] = max(stats["max_rounds"], rounds)
            for q0 in range(2):
                for h0 in range(rules.H + 1):
                    stats["root_queries"] += 1
                    ve = explicit_value(arena, rules, q0, h0, counts)
                    vd = fixed_past_value(arena, rules, q0, h0, counts)
                    vc = clock_layer_value(arena, rules, q0, h0, counts)
                    if ve != vd:
                        stats["mismatch_explicit_vs_deadline"] += 1
                        mismatches.append(dict(kind="deadline", arena=ai, counts=counts, q0=q0, h0=h0, explicit=ve, deadline=vd))
                    if ve != vc:
                        stats["mismatch_explicit_vs_clocklayer"] += 1
                        mismatches.append(dict(kind="clocklayer", arena=ai, counts=counts, q0=q0, h0=h0, explicit=ve, clock=vc))
                    v1 = one_mask_value(arena, rules, q0, h0, counts)
                    if alternating:
                        stats["corollary7_alternating_cases"] += 1
                        if v1 != ve:
                            stats["corollary7_mismatch"] += 1
                            mismatches.append(dict(kind="corollary7", arena=ai, counts=counts, q0=q0, h0=h0, explicit=ve, onemask=v1))
                    elif v1 != ve:
                        stats["corollary7_nonalternating_mismatch"] += 1
        if ai % 500 == 0:
            print(f"  [{tag}] arena {ai}/{len(arenas)}  {time.time()-t0:.0f}s", file=sys.stderr)
    stats["seconds"] = round(time.time() - t0, 1)
    return stats, mismatches


def run_random(seed=20260914, n=6000):
    rng = random.Random(seed)
    stats = dict(tag="random", arenas=n, root_queries=0, mismatch=0, max_rounds=0, max_keys=9)
    mismatches = []
    for i in range(n):
        n_keys = rng.randint(1, 9)
        arena = random_arena(rng, n_keys)
        r = rng.choice([2, 3, 4]); a = r + rng.choice([1, 2, 3])
        C = rng.randint(1, 8); H = rng.randint(C + 1, 12)
        rules = Rules(r, a, C, H)
        counts = tuple(rng.randrange(a) for _ in range(n_keys))
        A, B = masks(rules, counts)
        for P in (0, 1):
            _, rounds = deadline_vector(arena, rules, P, A, B)
            stats["max_rounds"] = max(stats["max_rounds"], rounds)
        for q0 in range(n_keys):
            for h0 in range(H + 1):
                stats["root_queries"] += 1
                ve = explicit_value(arena, rules, q0, h0, counts)
                vd = fixed_past_value(arena, rules, q0, h0, counts)
                if ve != vd:
                    stats["mismatch"] += 1
                    mismatches.append(dict(arena=[nd.__dict__ for nd in arena.nodes], rules=rules.__dict__, counts=counts, q0=q0, h0=h0, explicit=ve, deadline=vd))
    return stats, mismatches


if __name__ == "__main__":
    out = {}
    all_mm = []
    for rules, tag in [(Rules(2, 3, 2, 3), "r2a3C2H3"), (Rules(3, 5, 4, 6), "r3a5C4H6")]:
        s, mm = run_exhaustive(rules, tag)
        out[tag] = s; all_mm += mm
        print(json.dumps(s, indent=1))
    s, mm = run_random()
    out["random"] = s; all_mm += mm
    print(json.dumps(s, indent=1))
    json.dump(dict(stats=out, mismatches=all_mm[:200]), open("../results/exhaustive.json", "w"), indent=1)
    print("TOTAL MISMATCHES:", len(all_mm))
