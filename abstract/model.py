"""Independent implementation of the epoch-arena model from
"Fixed-Past Threshold Reduction for Finite Games with Repetition Rules, with an Exact Instantiation for FIDE Chess" (Sections III-V).

Written from the paper's definitions only. Two solvers:

  explicit_value   -- the explicit-history game: state (key, clock, occurrence counts),
                      evolving counts, current + intended-move repetition claims,
                      current + intended clock claims, automatic draws, exits.
  deadline_vector  -- the fixed-past deadline operator F_P of Eq. (1) with frozen masks
                      A = {c >= a-1}, B = {c >= r-1}; win iff h <= D_P(q).

If Theorem 1 is true the two must agree on every query.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, FrozenSet, List, Optional, Tuple

WIN0, WIN1, DRAW = 0, 1, 2          # outcomes
TERMINAL_OUTCOMES = (WIN0, WIN1, DRAW)


@dataclass(frozen=True)
class Node:
    terminal: Optional[int]                     # outcome if terminal, else None
    owner: int = 0                              # 0 or 1 (ignored for terminals)
    quiet: Tuple[int, ...] = ()                 # quiet successors (key indices)
    exits: Tuple[int, ...] = ()                 # exit outcomes available (subset of 0,1,2)


@dataclass(frozen=True)
class Arena:
    nodes: Tuple[Node, ...]

    @property
    def n(self):
        return len(self.nodes)


@dataclass(frozen=True)
class Rules:
    r: int   # claimable repetition occurrence
    a: int   # automatic repetition occurrence, a > r
    C: int   # claimable clock threshold
    H: int   # automatic clock threshold, H > C

    def __post_init__(self):
        assert 2 <= self.r < self.a and 1 <= self.C < self.H


def better_for(mover: int, x: int, y: int) -> int:
    """Return preferred outcome for `mover` among x, y."""
    rank = {mover: 2, DRAW: 1, 1 - mover: 0}
    return x if rank[x] >= rank[y] else y


# --------------------------------------------------------------------------
# Explicit-history game
# --------------------------------------------------------------------------

def explicit_value(arena: Arena, rules: Rules, q0: int, h0: int, counts: Tuple[int, ...]) -> int:
    """Game value (WIN0/WIN1/DRAW) of query (q0, h0, c) in the explicit game.

    `counts` are past occurrences *excluding* the current occurrence of q0.
    The current occurrence is added on arrival (N_p includes i = 0).
    Counts are capped at rules.a since larger values behave identically.
    """
    r, a, C, H = rules.r, rules.a, rules.C, rules.H
    nodes = arena.nodes
    cap = a

    @lru_cache(maxsize=None)
    def val(q: int, h: int, N: Tuple[int, ...]) -> int:
        # N already includes the current occurrence of q.
        node = nodes[q]
        if node.terminal is not None:
            return node.terminal                      # terminal priority
        if h >= H or N[q] >= a:
            return DRAW                               # automatic draws
        if not node.quiet and not node.exits:
            return DRAW                               # actionless nonterminal
        m = node.owner
        best = None
        # --- claims (separate actions yielding a draw) ---
        claim = False
        if N[q] >= r:                                 # (i) current repetition
            claim = True
        if h >= C:                                    # (iii) current clock
            claim = True
        for q2 in node.quiet:
            if N[q2] + 1 >= r:                        # (ii) intended repetition
                claim = True
            if h + 1 >= C:                            # (iv) intended clock
                claim = True
        if claim:
            best = DRAW
        # --- exits ---
        for o in node.exits:
            best = o if best is None else better_for(m, best, o)
        # --- quiet moves ---
        for q2 in node.quiet:
            N2 = list(N)
            N2[q2] = min(cap, N2[q2] + 1)
            v = val(q2, h + 1, tuple(N2))
            best = v if best is None else better_for(m, best, v)
        return best

    N0 = list(min(cap, c) for c in counts)
    N0[q0] = min(cap, N0[q0] + 1)
    return val(q0, h0, tuple(N0))


# --------------------------------------------------------------------------
# Fixed-past deadline operator (Eq. 3)
# --------------------------------------------------------------------------

def masks(rules: Rules, counts: Tuple[int, ...]) -> Tuple[FrozenSet[int], FrozenSet[int]]:
    B = frozenset(i for i, c in enumerate(counts) if c >= rules.r - 1)
    A = frozenset(i for i, c in enumerate(counts) if c >= rules.a - 1)
    return A, B


@lru_cache(maxsize=200000)
def deadline_vector(arena: Arena, rules: Rules, P: int,
                    A: FrozenSet[int], B: FrozenSet[int]) -> Tuple[Tuple[int, ...], int]:
    """Least fixed point of F_P by synchronous iteration from -1 on nonterminals.
    Returns (D, rounds) where rounds counts value-changing synchronous updates."""
    H, C = rules.H, rules.C
    nodes = arena.nodes
    n = arena.n

    def sat(z):
        return max(-1, z)

    d = [-1] * n
    for i, nd in enumerate(nodes):
        if nd.terminal is not None:
            d[i] = H if nd.terminal == P else -1

    def R(q):  # repetition claim available in the fixed-past game (Eq. 2)
        nd = nodes[q]
        return q in B or any(q2 in B for q2 in nd.quiet)

    def K(q):
        nd = nodes[q]
        if nd.owner == P:
            return H - 1
        return min(H - 1, C - 1 - (1 if nd.quiet else 0))

    def w(q2_or_exit, d, is_exit):
        if is_exit:
            return H - 1 if q2_or_exit == P else -1
        return sat(d[q2_or_exit] - 1)

    rounds = 0
    while True:
        new = list(d)
        for q, nd in enumerate(nodes):
            if nd.terminal is not None:
                continue
            if q in A or (not nd.quiet and not nd.exits) or (nd.owner != P and R(q)):
                new[q] = -1
                continue
            vals = [w(o, d, True) for o in nd.exits] + [w(q2, d, False) for q2 in nd.quiet]
            agg = max(vals) if nd.owner == P else min(vals)
            new[q] = min(K(q), agg)
        if new == d:
            return tuple(d), rounds
        d = new
        rounds += 1


def fixed_past_value(arena: Arena, rules: Rules, q0: int, h0: int, counts: Tuple[int, ...]) -> int:
    nd = arena.nodes[q0]
    if nd.terminal is not None:
        return nd.terminal
    A, B = masks(rules, counts)
    D0, _ = deadline_vector(arena, rules, 0, A, B)
    D1, _ = deadline_vector(arena, rules, 1, A, B)
    w0 = h0 <= D0[q0]
    w1 = h0 <= D1[q0]
    assert not (w0 and w1), "both players winning: operator inconsistent"
    return WIN0 if w0 else WIN1 if w1 else DRAW


def one_mask_value(arena: Arena, rules: Rules, q0: int, h0: int, counts: Tuple[int, ...]) -> int:
    """Corollary 4: automatic mask set to empty, root automatic status evaluated directly."""
    nd = arena.nodes[q0]
    if nd.terminal is not None:
        return nd.terminal
    A, B = masks(rules, counts)
    if q0 in A:
        return DRAW
    D0, _ = deadline_vector(arena, rules, 0, frozenset(), B)
    D1, _ = deadline_vector(arena, rules, 1, frozenset(), B)
    w0 = h0 <= D0[q0]
    w1 = h0 <= D1[q0]
    assert not (w0 and w1)
    return WIN0 if w0 else WIN1 if w1 else DRAW


# --------------------------------------------------------------------------
# Clock-layer backward solver on frozen masks (third method, Boolean layers)
# --------------------------------------------------------------------------

def clock_layer_value(arena: Arena, rules: Rules, q0: int, h0: int, counts: Tuple[int, ...]) -> int:
    """Backward minimax over (key, clock) with frozen masks; no deadlines, no counts."""
    r, a, C, H = rules.r, rules.a, rules.C, rules.H
    nodes = arena.nodes
    A, B = masks(rules, counts)

    @lru_cache(maxsize=None)
    def val(q, h):
        nd = nodes[q]
        if nd.terminal is not None:
            return nd.terminal
        if h >= H or q in A:
            return DRAW
        if not nd.quiet and not nd.exits:
            return DRAW
        m = nd.owner
        best = None
        claim = (q in B) or (h >= C) or any((q2 in B) or (h + 1 >= C) for q2 in nd.quiet)
        if claim:
            best = DRAW
        for o in nd.exits:
            best = o if best is None else better_for(m, best, o)
        for q2 in nd.quiet:
            v = val(q2, h + 1)
            best = v if best is None else better_for(m, best, v)
        return best

    return val(q0, h0)


# --------------------------------------------------------------------------
# Arena enumeration (paper Section VII domain)
# --------------------------------------------------------------------------

def node_configs(n_keys: int) -> List[Node]:
    """64 nonterminal configs (for 2 keys) + 3 terminals, matching the paper's 67."""
    from itertools import combinations
    cfgs: List[Node] = []
    keys = list(range(n_keys))
    quiet_subsets = []
    for k in range(n_keys + 1):
        quiet_subsets += [tuple(c) for c in combinations(keys, k)]
    exit_subsets = []
    for k in range(4):
        exit_subsets += [tuple(c) for c in combinations(TERMINAL_OUTCOMES, k)]
    for owner in (0, 1):
        for qs in quiet_subsets:
            for es in exit_subsets:
                cfgs.append(Node(None, owner, qs, es))
    for o in TERMINAL_OUTCOMES:
        cfgs.append(Node(o))
    return cfgs


def all_two_key_arenas() -> List[Arena]:
    cfgs = node_configs(2)
    return [Arena((x, y)) for x in cfgs for y in cfgs]


def random_arena(rng, n_keys: int) -> Arena:
    nodes = []
    for i in range(n_keys):
        if rng.random() < 0.15:
            nodes.append(Node(rng.choice(TERMINAL_OUTCOMES)))
            continue
        owner = rng.randrange(2)
        quiet = tuple(sorted(rng.sample(range(n_keys), rng.randint(0, min(3, n_keys)))))
        exits = tuple(sorted(rng.sample(TERMINAL_OUTCOMES, rng.randint(0, 3))))
        nodes.append(Node(None, owner, quiet, exits))
    return Arena(tuple(nodes))
