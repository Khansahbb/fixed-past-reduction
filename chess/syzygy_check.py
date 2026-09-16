"""Cross-check a solved .dl table (fresh history, clock 0) against Syzygy WDL and DTZ.

Mapping of semantics (side to move perspective):
  ours: win  iff D_stm >= 0;   loss iff D_other >= 0;   else draw
  syzygy wdl: 2 win, 1 cursed win (needs >50 moves: drawn under the 50-move claim), 0 draw,
              -1 blessed loss, -2 loss.   So 2 -> win, -2 -> loss, {1,0,-1} -> draw.
Also compares the deadline with DTZ where both are defined:
  for a winning side-to-move key, the largest clock at which the win survives should be
  C-1-... : we report the distribution of (D + DTZ) to expose the exact convention.
Usage: syzygy_check.py MATERIAL TABLEDIR SYZYGYDIR [sample]
"""
import sys, struct, json, random, collections
import chess, chess.syzygy

mat, tdir, sdir = sys.argv[1], sys.argv[2], sys.argv[3]
sample = int(sys.argv[4]) if len(sys.argv) > 4 else 0
PT = {'K': chess.KING, 'Q': chess.QUEEN, 'R': chess.ROOK, 'B': chess.BISHOP, 'N': chess.KNIGHT}
w, b = mat.split('v')
pieces = [(chess.WHITE, PT[c]) for c in w] + [(chess.BLACK, PT[c]) for c in b]
n = len(pieces)

with open(f'{tdir}/{mat}.dl', 'rb') as f:
    hdr = f.read(16); (nn,) = struct.unpack('<I', f.read(4)); assert nn == n
    nkeys = 2 << (6 * n)
    D0 = memoryview(f.read(nkeys * 2)).cast('h'); D1 = memoryview(f.read(nkeys * 2)).cast('h')
    legal = f.read(nkeys)

tb = chess.syzygy.open_tablebase(sdir)
idxs = [i for i in range(nkeys) if legal[i]]
if sample and sample < len(idxs):
    random.Random(1).shuffle(idxs); idxs = idxs[:sample]

conf = collections.Counter(); dtz_rel = collections.Counter(); disagreements = []
for idx in idxs:
    stm = idx & 1; k = idx >> 1; sq = [0] * n
    for i in range(n - 1, -1, -1): sq[i] = k & 63; k >>= 6
    bd = chess.Board(None)
    for (col, pt), s in zip(pieces, sq): bd.set_piece_at(s, chess.Piece(pt, col))
    bd.turn = chess.WHITE if stm == 0 else chess.BLACK
    if not bd.is_valid(): conf['invalid_for_python_chess'] += 1; continue
    ours = 'win' if (D0 if stm == 0 else D1)[idx] >= 0 else 'loss' if (D1 if stm == 0 else D0)[idx] >= 0 else 'draw'
    wdl = tb.probe_wdl(bd)
    syz = 'win' if wdl == 2 else 'loss' if wdl == -2 else 'draw'
    conf[(ours, syz, wdl)] += 1
    if ours != syz and len(disagreements) < 20:
        disagreements.append(dict(fen=bd.fen(), ours=ours, wdl=wdl, D_stm=(D0 if stm == 0 else D1)[idx], D_other=(D1 if stm == 0 else D0)[idx], dtz=tb.probe_dtz(bd)))
    if ours == 'win' and syz == 'win':
        dtz = tb.probe_dtz(bd); d = (D0 if stm == 0 else D1)[idx]
        dtz_rel[d + abs(dtz)] += 1     # deadline + plies-to-zeroing: constant if the two metrics agree
tb.close()
total = sum(v for k, v in conf.items() if isinstance(k, tuple))
agree = sum(v for k, v in conf.items() if isinstance(k, tuple) and k[0] == k[1])
out = dict(material=mat, compared=total, agree=agree, disagree=total - agree,
           confusion={f"{k[0]}/syz{k[2]}": v for k, v in conf.items() if isinstance(k, tuple)},
           deadline_plus_dtz_hist=dict(sorted(dtz_rel.items())), examples=disagreements)
print(json.dumps(out, indent=1))
json.dump(out, open(f'{tdir}/{mat}.syzygy.json', 'w'), indent=1)
