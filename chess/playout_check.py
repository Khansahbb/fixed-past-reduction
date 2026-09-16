"""Exact relation between deadline and plies to zeroing.
For sampled winning positions, play deadline-optimal moves for both sides (winner: a move winning at the
deadline; defender: the move that maximises the winner's remaining deadline, i.e. delays) until a capture
or mate, count plies t, and tabulate D + t together with who made the zeroing move and whether the
defender had a quiet alternative at that moment.
Usage: playout_check.py MATERIAL TABLEDIR SAMPLE
"""
import sys, struct, json, random, collections, chess
mat, tdir = sys.argv[1], sys.argv[2]; sample = int(sys.argv[3])
PT = {'K': chess.KING, 'Q': chess.QUEEN, 'R': chess.ROOK, 'B': chess.BISHOP, 'N': chess.KNIGHT}
w, b = mat.split('v'); pieces = [(chess.WHITE, PT[c]) for c in w] + [(chess.BLACK, PT[c]) for c in b]; n = len(pieces)
f = open(f'{tdir}/{mat}.dl', 'rb'); f.read(20); nk = 2 << (6 * n)
D0 = memoryview(f.read(nk * 2)).cast('h'); D1 = memoryview(f.read(nk * 2)).cast('h'); legal = f.read(nk)
lower = {}
def load(m):
    ww, bb = m.split('v'); pcs = [(chess.WHITE, PT[c]) for c in ww] + [(chess.BLACK, PT[c]) for c in bb]; nn = len(pcs)
    g = open(f'{tdir}/{m}.dl', 'rb'); g.read(20); nk2 = 2 << (6 * nn)
    return pcs, memoryview(g.read(nk2 * 2)).cast('h'), memoryview(g.read(nk2 * 2)).cast('h')
PCH = {v: k for k, v in PT.items()}
def exit_wins(bd, P):
    # bd is the position after the capture; P is the target colour
    wm = ''.join(PCH[p.piece_type] for s, p in sorted(bd.piece_map().items()) if p.color == chess.WHITE)
    bm = ''.join(PCH[p.piece_type] for s, p in sorted(bd.piece_map().items()) if p.color == chess.BLACK)
    def order(part, ref):
        out = 'K'; rest = [c for c in part if c != 'K']
        for c in ref:
            if c != 'K' and c in rest: out += c; rest.remove(c)
        return out + ''.join(rest)
    m = order(wm, w) + 'v' + order(bm, b)
    if m == 'KvK': return False
    if m not in lower: lower[m] = load(m)
    pcs, E0, E1 = lower[m]
    k = 0; used = set()
    for (col, pt) in pcs:
        sq = [x for x in bd.pieces(pt, col) if x not in used][0]; used.add(sq); k = k * 64 + sq
    j = k * 2 + (0 if bd.turn else 1)
    return (E0 if P == chess.WHITE else E1)[j] >= 0

def key(bd):
    k = 0; used = set()
    for (col, pt) in pieces:
        s = [s for s in bd.pieces(pt, col) if s not in used][0]; used.add(s); k = k * 64 + s
    return k * 2 + (0 if bd.turn else 1)
DEBUG = len(sys.argv) > 4
rng = random.Random(3); idxs = [i for i in range(nk) if legal[i]]; rng.shuffle(idxs)
hist = collections.Counter(); seen = 0
for idx in idxs:
    stm = idx & 1; k = idx >> 1; sq = [0] * n
    for i in range(n - 1, -1, -1): sq[i] = k & 63; k >>= 6
    Dm = D0 if stm == 0 else D1
    if Dm[idx] < 0: continue
    bd = chess.Board(None)
    for (col, pt), s in zip(pieces, sq): bd.set_piece_at(s, chess.Piece(pt, col))
    bd.turn = (stm == 0)
    if not bd.is_valid(): continue
    P = bd.turn; D = Dm[idx]; t = 0; who = None; alt = None
    while True:
        moves = list(bd.legal_moves)
        if not moves: who = 'mate-terminal'; break
        best = None
        for mv in moves:
            if bd.is_capture(mv):
                bd.push(mv); ok = exit_wins(bd, P); bd.pop()
                if bd.turn == P: val = 10**6 if ok else -10**7          # winner: only a winning capture ends the line
                else: val = -10**6 if ok else 10**7                    # defender: a capture that keeps P winning is a last resort; one that refutes P cannot exist at winning keys
            else:
                bd.push(mv); d = Dm[key(bd)]; bd.pop()
                val = d if bd.turn == P else (-d if d >= 0 else -10**5)   # defender minimises the winner's deadline
            if best is None or val > best[0]: best = (val, mv)
        mv = best[1]; t += 1
        if DEBUG: print('  ply', t, 'side', 'P' if bd.turn==P else 'def', mv.uci(), 'val', best[0], 'fen', bd.fen())
        if bd.is_capture(mv):
            who = 'winner' if bd.turn == P else 'defender'
            if who == 'defender': alt = any(not bd.is_capture(m) for m in moves)
            break
        bd.push(mv)
        if bd.is_checkmate(): who = 'mate'; break
        if t > 400: who = 'runaway'; break
    hist[(D + t if who != 'runaway' else -1, who, alt)] += 1
    if DEBUG and D + t < 100 and who == 'winner':
        print('LOW', D, t, who); break
    seen += 1
    if seen >= sample: break
out = {f"{k[0]}|{k[1]}|alt={k[2]}": v for k, v in sorted(hist.items(), key=lambda x: -x[1])}
print(json.dumps(dict(material=mat, sampled=seen, D_plus_t=out)))
json.dump(dict(material=mat, sampled=seen, D_plus_t=out), open(f'{tdir}/{mat}.playout.json', 'w'), indent=1)
