"""Executed checks for the algorithmic propositions of the paper.

  bucket_deadline   Proposition (Bucket computation): label-setting over buckets, compared with
                    the synchronous fixed point on every two-key arena and mask, and on random arenas.
  certificate       Corollary (Certificate): every single-entry mutation of the true deadline vector
                    must fail the local test d = F_P d.
  path_budget       Proposition (Path-clock budget): exhaustive enumeration of key-positional policies
                    on small arenas; max budget must equal the deadline.
  labelled_lift     Proposition (Labelled encodings): random encoded arenas with duplicated keys and
                    lifted masks; encoded deadlines must equal the physical ones composed with the projection.
  arrival           Proposition (Arrival scoring): on alternating arenas the arrival game must have the
                    explicit-history root value.

Usage: python check_props.py [quick]      writes results/props.json
"""
from __future__ import annotations
import json, random, sys, time
from functools import lru_cache
from itertools import product
from model import *


def caps_and_blocked(arena, rules, P, A, B):
    H, C = rules.H, rules.C
    nodes = arena.nodes

    def K(q):
        nd = nodes[q]
        if nd.owner == P:
            return H - 1
        return min(H - 1, C - 1 - (1 if nd.quiet else 0))

    def blocked(q):
        nd = nodes[q]
        if q in A or (not nd.quiet and not nd.exits):
            return True
        return nd.owner != P and (q in B or any(q2 in B for q2 in nd.quiet))
    return K, blocked


def apply_F(arena, rules, P, A, B, d):
    """One application of the operator F_P to the vector d (terminal entries prescribed)."""
    H = rules.H
    nodes = arena.nodes
    K, blocked = caps_and_blocked(arena, rules, P, A, B)
    out = list(d)
    for q, nd in enumerate(nodes):
        if nd.terminal is not None:
            out[q] = H if nd.terminal == P else -1
            continue
        if blocked(q):
            out[q] = -1
            continue
        vals = [H - 1 if o == P else -1 for o in nd.exits] + [max(-1, d[q2] - 1) for q2 in nd.quiet]
        agg = max(vals) if nd.owner == P else min(vals)
        out[q] = min(K(q), agg)
    return out


def bucket_deadline(arena, rules, P, A, B):
    """Label-setting computation of D_P through ranks rho = H-1-D_P, as in the proof of the
    bucket proposition. Returns the deadline vector."""
    H = rules.H
    nodes = arena.nodes
    n = arena.n
    K, blocked = caps_and_blocked(arena, rules, P, A, B)
    rev = [[] for _ in range(n)]                    # rev[x] = keys with a quiet move to x
    for q, nd in enumerate(nodes):
        if nd.terminal is None:
            for q2 in nd.quiet:
                rev[q2].append(q)
    rank = [None] * n                                # settled rank, None = unsettled
    buckets = [[] for _ in range(H)]
    remaining = [0] * n                              # defending keys: reports still awaited
    best = [-1] * n                                  # defending keys: max report so far
    floor = [0] * n
    for q, nd in enumerate(nodes):
        if nd.terminal is not None:
            continue
        floor[q] = H - 1 - K(q)
        if nd.owner != P:
            remaining[q] = len(nd.exits) + len(nd.quiet)

    def propose(q, cost):
        cand = max(floor[q], cost)
        if cand < H:
            buckets[cand].append(q)

    def report(q, cost):
        """A report of `cost` reaches key q through one of its actions."""
        nd = nodes[q]
        if nd.terminal is not None or blocked(q) or rank[q] is not None:
            return
        if nd.owner == P:
            propose(q, cost)
        else:
            remaining[q] -= 1
            best[q] = max(best[q], cost)
            if remaining[q] == 0:
                propose(q, best[q])

    # initial reports from exits and terminals
    for q, nd in enumerate(nodes):
        if nd.terminal is not None:
            continue
        for o in nd.exits:
            if o == P:
                report(q, 0)
        for q2 in nd.quiet:
            t = nodes[q2]
            if t.terminal is not None and t.terminal == P:
                report(q, 0)
    # scan
    for k in range(H):
        i = 0
        while i < len(buckets[k]):
            q = buckets[k][i]; i += 1
            if rank[q] is not None:
                continue
            rank[q] = k
            for p in rev[q]:
                report(p, k + 1)
    D = []
    for q, nd in enumerate(nodes):
        if nd.terminal is not None:
            D.append(H if nd.terminal == P else -1)
        else:
            D.append(-1 if rank[q] is None else H - 1 - rank[q])
    return tuple(D)


def policies(arena, P):
    """All key-positional policies for P: one action at every P-owned key."""
    nodes = arena.nodes
    pkeys = [q for q, nd in enumerate(nodes) if nd.terminal is None and nd.owner == P]
    choices = [([('x', o) for o in nodes[q].exits] + [('q', q2) for q2 in nodes[q].quiet]) or [('none', None)] for q in pkeys]
    for pick in product(*choices):
        yield dict(zip(pkeys, pick))


def budget_max(arena, rules, P, A, B, q0):
    """max over admissible policies of b(sigma) from q0, or -1; None at terminals."""
    H = rules.H
    nodes = arena.nodes
    if nodes[q0].terminal is not None:
        return None
    K, blocked = caps_and_blocked(arena, rules, P, A, B)
    best = -1
    for sigma in policies(arena, P):
        state = {'ok': True, 'budget': H}

        def go(q, i, path):
            if not state['ok']:
                return
            nd = nodes[q]
            if nd.terminal is not None:
                if nd.terminal != P:
                    state['ok'] = False
                return
            if q in path or blocked(q):
                state['ok'] = False
                return
            state['budget'] = min(state['budget'], K(q) - i)
            if nd.owner == P:
                kind, a = sigma[q]
                if kind == 'x':
                    if a != P:
                        state['ok'] = False
                    return
                go(a, i + 1, path + (q,))
            else:
                if any(o != P for o in nd.exits):
                    state['ok'] = False
                    return
                for q2 in nd.quiet:
                    go(q2, i + 1, path + (q,))
        go(q0, 0, ())
        if state['ok']:
            best = max(best, state['budget'])
    return best


def lift(arena, rng, max_rep=3):
    """Random encoded arena: each key gets 1..max_rep representatives; quiet successors of a
    representative are a random covering multiset of representatives of the physical successors."""
    reps = []
    enc_nodes = []
    pi = []
    for q, nd in enumerate(arena.nodes):
        k = 1 if nd.terminal is not None else rng.randint(1, max_rep)
        reps.append(list(range(len(pi), len(pi) + k)))
        pi += [q] * k
    for q, nd in enumerate(arena.nodes):
        for _ in reps[q]:
            if nd.terminal is not None:
                enc_nodes.append(Node(nd.terminal))
                continue
            quiet = []
            for q2 in nd.quiet:
                cand = reps[q2]
                chosen = {rng.choice(cand)}                       # at least one representative
                for c in cand:
                    if rng.random() < 0.5:
                        chosen.add(c)
                quiet += sorted(chosen)
                if rng.random() < 0.3:                            # a duplicated action
                    quiet.append(rng.choice(cand))
            enc_nodes.append(Node(None, nd.owner, tuple(quiet), nd.exits))
    return Arena(tuple(enc_nodes)), pi


def arrival_value(arena, rules, q0, h0, A, B):
    """Root value of the arrival game of the arrival-scoring proposition (alternation assumed)."""
    C, H = rules.C, rules.H
    nodes = arena.nodes
    nd0 = nodes[q0]
    if nd0.terminal is not None:
        return nd0.terminal
    if q0 in A:
        return DRAW

    @lru_cache(maxsize=None)
    def val(q, h, line):
        nd = nodes[q]
        if nd.terminal is not None:
            return nd.terminal
        if h >= H:
            return DRAW
        if not nd.quiet and not nd.exits:
            return DRAW
        m = nd.owner
        best = None
        claim = (h >= C) or any(h + 1 >= C for _ in nd.quiet)
        if h == h0 and q == q0 and len(line) == 1 and q0 in B:
            claim = True                                          # retained root claim
        if claim:
            best = DRAW
        for o in nd.exits:
            best = o if best is None else better_for(m, best, o)
        for q2 in nd.quiet:
            t = nodes[q2]
            if t.terminal is not None:
                v = t.terminal
            elif q2 in B or q2 in line:
                v = DRAW
            else:
                v = val(q2, h + 1, line | frozenset([q2]))
            best = v if best is None else better_for(m, best, v)
        return best
    return val(q0, h0, frozenset([q0]))


def random_alternating_arena(rng, n_keys):
    owners = [rng.randrange(2) for _ in range(n_keys)]
    term = [rng.random() < 0.15 for _ in range(n_keys)]
    nodes = []
    for i in range(n_keys):
        if term[i]:
            nodes.append(Node(rng.choice(TERMINAL_OUTCOMES)))
            continue
        allowed = [j for j in range(n_keys) if term[j] or owners[j] != owners[i]]
        quiet = tuple(sorted(rng.sample(allowed, rng.randint(0, min(3, len(allowed))))))
        exits = tuple(sorted(rng.sample(TERMINAL_OUTCOMES, rng.randint(0, 3))))
        nodes.append(Node(None, owners[i], quiet, exits))
    return Arena(tuple(nodes))


def main(quick=False):
    out = {}
    t0 = time.time()
    # 1. bucket vs synchronous, exhaustive two-key domain
    for rules in (Rules(2, 3, 2, 3), Rules(3, 5, 4, 6)):
        arenas = all_two_key_arenas()
        cmp = mis = 0
        for arena in arenas:
            for counts in product(range(rules.a), repeat=2):
                A, B = masks(rules, counts)
                for P in (0, 1):
                    D, _ = deadline_vector(arena, rules, P, A, B)
                    Db = bucket_deadline(arena, rules, P, A, B)
                    cmp += 1
                    if D != Db:
                        mis += 1
        out[f"bucket_twokey_{rules.r}{rules.a}{rules.C}{rules.H}"] = dict(vectors=cmp, mismatch=mis)
        print("bucket two-key", rules, cmp, mis, f"{time.time()-t0:.0f}s", file=sys.stderr)
    # 2. random arenas: bucket, certificate mutations, lift
    rng = random.Random(20260916)
    N = 2000 if quick else 20000
    bcmp = bmis = 0
    cert_ok = cert_mut = cert_accept = 0
    lift_cmp = lift_mis = 0
    for i in range(N):
        n_keys = rng.randint(1, 12)
        arena = random_arena(rng, n_keys)
        r = rng.choice([2, 3, 4]); a = r + rng.choice([1, 2, 3])
        C = rng.randint(1, 10); H = rng.randint(C + 1, 16)
        rules = Rules(r, a, C, H)
        counts = tuple(rng.randrange(a) for _ in range(n_keys))
        A, B = masks(rules, counts)
        for P in (0, 1):
            D, _ = deadline_vector(arena, rules, P, A, B)
            Db = bucket_deadline(arena, rules, P, A, B)
            bcmp += 1
            bmis += D != Db
            # certificate: true vector passes
            if tuple(apply_F(arena, rules, P, A, B, list(D))) == D:
                cert_ok += 1
            # every single-entry mutation must fail
            for q, nd in enumerate(arena.nodes):
                if nd.terminal is not None:
                    continue
                for v in range(-1, H):
                    if v == D[q]:
                        continue
                    d = list(D); d[q] = v
                    cert_mut += 1
                    if apply_F(arena, rules, P, A, B, d) == d:
                        cert_accept += 1
        # lift
        enc, pi = lift(arena, rng)
        At = frozenset(i2 for i2, q in enumerate(pi) if q in A)
        Bt = frozenset(i2 for i2, q in enumerate(pi) if q in B)
        for P in (0, 1):
            D, _ = deadline_vector(arena, rules, P, A, B)
            Dt, _ = deadline_vector(enc, rules, P, At, Bt)
            lift_cmp += 1
            lift_mis += any(Dt[i2] != D[pi[i2]] for i2 in range(len(pi)))
    out["bucket_random"] = dict(vectors=bcmp, mismatch=bmis)
    out["certificate"] = dict(true_vectors=2 * N, true_pass=cert_ok, mutations=cert_mut, mutations_accepted=cert_accept)
    out["lift"] = dict(vectors=lift_cmp, mismatch=lift_mis)
    print("random", out["bucket_random"], out["certificate"], out["lift"], f"{time.time()-t0:.0f}s", file=sys.stderr)
    # 3. path budget on small arenas
    M = 300 if quick else 3000
    pb_cmp = pb_mis = 0
    for i in range(M):
        n_keys = rng.randint(1, 6)
        arena = random_arena(rng, n_keys)
        r = rng.choice([2, 3]); a = r + rng.choice([1, 2])
        C = rng.randint(1, 6); H = rng.randint(C + 1, 9)
        rules = Rules(r, a, C, H)
        counts = tuple(rng.randrange(a) for _ in range(n_keys))
        A, B = masks(rules, counts)
        for P in (0, 1):
            D, _ = deadline_vector(arena, rules, P, A, B)
            for q0 in range(n_keys):
                b = budget_max(arena, rules, P, A, B, q0)
                if b is None:
                    continue
                pb_cmp += 1
                pb_mis += (max(-1, b) != D[q0])
    out["path_budget"] = dict(queries=pb_cmp, mismatch=pb_mis)
    print("budget", out["path_budget"], f"{time.time()-t0:.0f}s", file=sys.stderr)
    # 4. arrival game on alternating arenas
    Q = 1000 if quick else 10000
    ar_cmp = ar_mis = 0
    for i in range(Q):
        n_keys = rng.randint(1, 8)
        arena = random_alternating_arena(rng, n_keys)
        r = rng.choice([2, 3, 4]); a = r + rng.choice([1, 2])
        C = rng.randint(1, 8); H = rng.randint(C + 1, 12)
        rules = Rules(r, a, C, H)
        # counts live on nonterminal keys only (Definition of the explicit game); terminals get 0
        counts = tuple(0 if nd.terminal is not None else rng.randrange(a) for nd in arena.nodes)
        A, B = masks(rules, counts)
        for q0 in range(n_keys):
            for h0 in range(0, H + 1, max(1, H // 4)):
                ve = explicit_value(arena, rules, q0, h0, counts)
                va = arrival_value(arena, rules, q0, h0, A, B)
                ar_cmp += 1
                ar_mis += ve != va
    out["arrival"] = dict(queries=ar_cmp, mismatch=ar_mis)
    print("arrival", out["arrival"], f"{time.time()-t0:.0f}s", file=sys.stderr)
    out["seconds"] = round(time.time() - t0, 1)
    json.dump(out, open("../results/props.json", "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(quick=len(sys.argv) > 1 and sys.argv[1] == "quick")
