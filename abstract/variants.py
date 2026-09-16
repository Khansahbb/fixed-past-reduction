"""Check the hypothesis-necessity counterexamples proposed in the perspective review (R3-W3, R3-W4)
by explicit computation on variant rule semantics.

V1 reward : the r-th occurrence WINS for the player who creates it (instead of draw).
V2 penalty: the player who creates the r-th occurrence LOSES.
V3 window : defender clock claims available only when h in {1,2} (non-monotone), no repetition claims.
For each we compute the explicit-history value and the frozen-mask deadline value; a mismatch
shows the theorem fails when that hypothesis is dropped.
"""
from functools import lru_cache
from model import *

def explicit_variant(arena, rules, q0, h0, counts, variant):
    r, a, C, H = rules.r, rules.a, rules.C, rules.H
    nodes = arena.nodes
    @lru_cache(maxsize=None)
    def val(q, h, N, mover_created):
        nd = nodes[q]
        if nd.terminal is not None: return nd.terminal
        if variant == 'reward' and N[q] >= r:  # player who moved here wins
            return mover_created
        if variant == 'penalty' and N[q] >= r:
            return 1 - mover_created
        if h >= H or (variant not in ('reward', 'penalty') and N[q] >= a): return DRAW
        if not nd.quiet and not nd.exits: return DRAW
        m = nd.owner; best = None
        claim = False
        if variant == 'window':
            if m != 0 and h in (1, 2): claim = True          # defender-only window claim
        if claim: best = DRAW
        for o in nd.exits:
            best = o if best is None else better_for(m, best, o)
        for q2 in nd.quiet:
            N2 = list(N); N2[q2] = min(a, N2[q2] + 1)
            v = val(q2, h + 1, tuple(N2), m)
            best = v if best is None else better_for(m, best, v)
        return best
    N0 = list(min(a, c) for c in counts); N0[q0] = min(a, N0[q0] + 1)
    return val(q0, h0, tuple(N0), 1 - nodes[q0].owner)

# V1 reward: target-owned x with quiet self-loop, no exit; r=2; explicit: target wins by looping once.
ar = Arena((Node(None, 0, (0,), ()),)); R = Rules(2, 3, 2, 4)
print('V1 reward   explicit', explicit_variant(ar, R, 0, 0, (0,), 'reward'), ' frozen-mask', fixed_past_value(ar, R, 0, 0, (0,)))
# V2 penalty: x(target) -> y(defender) -> x only; c(x)=r-2=1 with r=3: defender forced to return to x, creating 3rd occurrence -> loses.
ar = Arena((Node(None, 0, (1,), ()), Node(None, 1, (0,), ()))); R = Rules(3, 5, 4, 6)
print('V2 penalty  explicit', explicit_variant(ar, R, 0, 0, (1, 0), 'penalty'), ' frozen-mask', fixed_past_value(ar, R, 0, 0, (1, 0)))
# V3 window: x(target) self-loop + edge to y(defender); y -> z(target); z -> W0 exit. r=2,a=3,H=6. Defender may claim only at h in {1,2}.
ar = Arena((Node(None, 0, (0, 1), ()), Node(None, 1, (2,), ()), Node(None, 0, (), (WIN0,))))
R = Rules(2, 3, 5, 6)
# frozen-mask model with monotone clock claims cannot express the window; compare against the monotone model's answer
print('V3 window   explicit', explicit_variant(ar, R, 0, 0, (0, 0, 0), 'window'), ' frozen-mask(monotone semantics)', fixed_past_value(ar, R, 0, 0, (0, 0, 0)))
