"""Fragility of won positions under supplied history.

For each won position with the winner to move (fresh history, clock 0), count the winning moves
at clock 0. A position with exactly one winning move is fragile. If the position that move reaches
has occurred twice earlier in the game, the defender claims a draw on arrival (current claim) or the
mask puts the successor in B, and the exact value of the position becomes a draw, with no alternative.

Winning move at clock 0 for target P from key q (P to move):
  quiet to q' with D_P(q') >= 1, or a capture whose lower-material fresh value is a P win.
Usage: fragility.py MATERIAL TABLEDIR [sample]
"""
import sys, struct, json, random, collections
import chess

mat, tdir = sys.argv[1], sys.argv[2]
sample = int(sys.argv[3]) if len(sys.argv) > 3 else 200000
PT = {'K': chess.KING, 'Q': chess.QUEEN, 'R': chess.ROOK, 'B': chess.BISHOP, 'N': chess.KNIGHT}
PCH = {v: k for k, v in PT.items()}

def load(m):
    w, b = m.split('v'); pcs = [(chess.WHITE, PT[c]) for c in w] + [(chess.BLACK, PT[c]) for c in b]
    n = len(pcs)
    with open(f'{tdir}/{m}.dl', 'rb') as f:
        f.read(16); (nn,) = struct.unpack('<I', f.read(4)); nkeys = 2 << (6 * n)
        D0 = memoryview(f.read(nkeys * 2)).cast('h'); D1 = memoryview(f.read(nkeys * 2)).cast('h'); legal = f.read(nkeys)
    return pcs, n, D0, D1, legal

pcs, n, D0, D1, legal = load(mat)
lower = {}
def lower_table(m):
    if m == 'KvK': return None
    if m not in lower: lower[m] = load(m)
    return lower[m]

def index(pcs_order, board, stm):
    idx = 0
    for col, pt in pcs_order:
        sqs = list(board.pieces(pt, col))
        # deterministic assignment for duplicate piece types: consume in ascending square order
        s = sqs.pop(0); board.remove_piece_at(s); idx = idx * 64 + s
    return idx * 2 + stm

def material_after(board):
    w = ''.join(PCH[p.piece_type] for s, p in sorted(board.piece_map().items()) if p.color == chess.WHITE)
    b = ''.join(PCH[p.piece_type] for s, p in sorted(board.piece_map().items()) if p.color == chess.BLACK)
    # order: kings first, then others in the order of the original material string when possible
    def order(part, ref):
        out = 'K'; rest = [c for c in part if c != 'K']
        for c in ref:
            if c != 'K' and c in rest: out += c; rest.remove(c)
        return out + ''.join(rest)
    wm, bm = mat.split('v')
    return order(w, wm) + 'v' + order(b, bm)

rng = random.Random(2)
nkeys = 2 << (6 * n)
idxs = [i for i in range(nkeys) if legal[i]]
rng.shuffle(idxs)
stats = collections.Counter(); winmove_hist = collections.Counter()
seen = 0
for idx in idxs:
    stm = idx & 1; k = idx >> 1; sq = [0] * n
    for i in range(n - 1, -1, -1): sq[i] = k & 63; k >>= 6
    Dm = D0 if stm == 0 else D1
    if Dm[idx] < 0: continue                     # not won for the side to move
    bd = chess.Board(None)
    for (col, pt), s in zip(pcs, sq): bd.set_piece_at(s, chess.Piece(pt, col))
    bd.turn = chess.WHITE if stm == 0 else chess.BLACK
    if not bd.is_valid(): continue
    P = stm; wins = 0; qwins = 0; cwins = 0
    for mv in bd.legal_moves:
        cap = bd.is_capture(mv); bd.push(mv)
        if cap:
            m2 = material_after(bd); L = lower_table(m2)
            if L is None: ok = False
            else:
                pcs2, n2, E0, E1, leg2 = L
                b2 = bd.copy(); j = index(pcs2, b2, 1 - stm)
                ok = (E0 if P == 0 else E1)[j] >= 0
        else:
            b2 = bd.copy(); j = index(pcs, b2, 1 - stm)
            ok = Dm[j] >= 1
            if ok and bd.is_checkmate(): cap = True      # a mating move ends the game; the successor cannot recur
        bd.pop()
        wins += ok
        if ok and cap: cwins += 1
        if ok and not cap: qwins += 1
    seen += 1
    winmove_hist[min(wins, 5)] += 1
    if wins == 0: stats['inconsistent'] += 1
    if wins == 1: stats['fragile'] += 1
    if cwins == 0 and qwins == 1: stats['fragile_quiet'] += 1
    if cwins == 0: stats['no_winning_capture'] += 1
    if seen >= sample: break
out = dict(material=mat, won_positions_sampled=seen, fragile=stats['fragile'], fragile_frac=round(stats['fragile'] / max(1, seen), 4), fragile_quiet=stats['fragile_quiet'], fragile_quiet_frac=round(stats['fragile_quiet'] / max(1, seen), 4), no_winning_capture=stats['no_winning_capture'],
           winning_move_count_hist={str(k): v for k, v in sorted(winmove_hist.items())}, inconsistent=stats['inconsistent'])
print(json.dumps(out)); json.dump(out, open(f'{tdir}/{mat}.fragility.json', 'w'), indent=1)
