"""Build the LaTeX result tables for the paper from run.log, *.syzygy.json and *.fragility.json."""
import json, os, glob
ORDER = ['KQvK', 'KRvK', 'KBvK', 'KNvK', 'KQvKQ', 'KQvKR', 'KQvKB', 'KQvKN', 'KRvKR', 'KRvKB', 'KRvKN', 'KBvKB', 'KBvKN', 'KNvKN',
         'KQQvK', 'KQRvK', 'KQBvK', 'KQNvK', 'KRRvK', 'KRBvK', 'KRNvK', 'KBBvK', 'KBNvK', 'KNNvK']
THREE = {'KQvK': dict(legal=368452, wtm=dict(win=144508, draw=0, loss=0), rounds=17, seconds=0.8),
         'KRvK': dict(legal=399112, wtm=dict(win=175168, draw=0, loss=0), rounds=26, seconds=1.5),
         'KBvK': dict(legal=417228, wtm=dict(win=0, draw=193284, loss=0), rounds=1, seconds=0.2),
         'KNvK': dict(legal=429440, wtm=dict(win=0, draw=205496, loss=0), rounds=1, seconds=0.1)}
seen = dict(THREE)
for l in open('tables/run.log'):
    if l.startswith('{'):
        r = json.loads(l); seen[r['material']] = r

def num(x): return f"{x:,}".replace(',', '{,}')

rows = []
for m in ORDER:
    r = seen[m]; w = r['wtm']
    rows.append(f"{m} & {num(r['legal'])} & {num(w['win'])} & {num(w['draw'])} & {num(w['loss'])} & {r['rounds']} & {r['seconds']:.0f}\\\\")
chess_tab = ("\\begin{table}[t]\\centering\\small\n"
    "\\caption{Pawnless materials solved under the FIDE repetition and move-clock rules with fresh history. Win, draw and loss are for White to move; legal keys count both sides to move. Rounds are iterations of~\\eqref{eq:F} until no value changes; time is on an eight-core desktop.}\n"
    "\\label{tab:chess}\n\\begin{tabular}{@{}lrrrrrr@{}}\\toprule\nMaterial & Legal keys & Win & Draw & Loss & Rounds & s\\\\ \\midrule\n"
    + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n\\end{table}")

# Syzygy table
srows = []; tot_cmp = 0; tot_dis = 0
for m in ORDER:
    p = f'tables/{m}.syzygy.json'
    if not os.path.exists(p): srows.append(f"{m} & pending & & & \\\\"); continue
    d = json.load(open(p)); h = d['deadline_plus_dtz_hist']
    tot_cmp += d['compared']; tot_dis += d['disagree']
    srows.append(f"{m} & {num(d['compared'])} & {d['disagree']} & {num(h.get('100', 0))} & {num(h.get('99', 0))} & {num(h.get('150', 0))}\\\\")
syz_tab = ("\\begin{table}[t]\\centering\\small\n"
    "\\caption{Agreement with Syzygy on fresh-history win/draw/loss (three-piece materials in full, four-piece materials on a uniform random sample), and the value of $D+\\mathrm{DTZ}$ on winning positions: 100 when Syzygy's rounded DTZ50'' equals the exact plies to zeroing, 99 when it is one less, 150 when the winning move captures or mates immediately.}\n"
    "\\label{tab:syzygy}\n\\begin{tabular}{@{}lrrrrr@{}}\\toprule\nMaterial & Compared & Disagree & $D{+}\\mathrm{DTZ}{=}100$ & ${=}99$ & ${=}150$\\\\ \\midrule\n"
    + "\n".join(srows) + f"\n\\midrule\nTotal & {num(tot_cmp)} & {tot_dis} & & & \\\\\n\\bottomrule\n\\end{{tabular}}\n\\end{{table}}")

# fragility sentence
fr = []
for m in ORDER:
    p = f'tables/{m}.fragility.json'
    if os.path.exists(p):
        d = json.load(open(p))
        if len(m) < 5 or 'fragile_quiet' not in d: continue
        fr.append((m, d['won_positions_sampled'], d['fragile_quiet'], d['fragile_quiet_frac']))
if fr:
    hi = max(fr, key=lambda x: x[3]); lo = min(fr, key=lambda x: x[3])
    tot = sum(x[1] for x in fr); frag = sum(x[2] for x in fr)
    frag_txt = (f"Over {num(tot)} sampled won positions across the four-piece materials, {num(frag)} ({100*frag/tot:.1f}\\%) are fragile; "
                f"the fraction ranges from {100*lo[3]:.1f}\\% in {lo[0]} to {100*hi[3]:.1f}\\% in {hi[0]}.")
else:
    frag_txt = "FRAGILITY"
open('tables/chess_table.tex', 'w').write(chess_tab)
open('tables/syzygy_table.tex', 'w').write(syz_tab)
open('tables/fragility.txt', 'w').write(frag_txt)
print(chess_tab[:300]); print(frag_txt)
