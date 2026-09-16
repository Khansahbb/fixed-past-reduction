"""Adversarial red-team: dense 3-6 key arenas, many cycles, self-loops, high past counts,
tight clocks. Looks for any query where explicit != deadline."""
import random, json, sys
from model import *
rng = random.Random(7)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
mm = []; queries = 0
for i in range(N):
    k = rng.randint(3, 6)
    nodes = []
    for j in range(k):
        if rng.random() < 0.1:
            nodes.append(Node(rng.choice(TERMINAL_OUTCOMES))); continue
        deg = rng.randint(1, k)                        # dense: at least one quiet edge
        quiet = tuple(sorted(rng.sample(range(k), deg)))
        exits = tuple(sorted(rng.sample(TERMINAL_OUTCOMES, rng.choice([0, 0, 1, 1, 2, 3]))))
        nodes.append(Node(None, rng.randrange(2), quiet, exits))
    arena = Arena(tuple(nodes))
    r = rng.choice([2, 3]); a = r + rng.choice([1, 2]); C = rng.randint(1, 5); H = rng.randint(C + 1, C + 5)
    rules = Rules(r, a, C, H)
    counts = tuple(rng.choice([0, r - 2, r - 1, a - 2, a - 1]) if rng.random() < 0.8 else 0 for _ in range(k))
    counts = tuple(max(0, c) for c in counts)
    for q0 in range(k):
        for h0 in range(H + 1):
            queries += 1
            ve = explicit_value(arena, rules, q0, h0, counts)
            vd = fixed_past_value(arena, rules, q0, h0, counts)
            if ve != vd:
                mm.append(dict(arena=[nd.__dict__ for nd in nodes], rules=rules.__dict__, counts=counts, q0=q0, h0=h0, explicit=ve, deadline=vd))
    if i % 5000 == 0: print(i, queries, len(mm), file=sys.stderr)
json.dump(dict(arenas=N, queries=queries, mismatches=mm[:50], n_mismatch=len(mm)), open('../results/redteam_dense.json', 'w'), indent=1)
print(json.dumps(dict(arenas=N, queries=queries, n_mismatch=len(mm))))
