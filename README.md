<h1 align="center">Fixed-past threshold reduction</h1>

<p align="center">
  Repetition rules make a position's value depend on its history.<br>
  This work proves the whole history reduces to two sets of positions, and instantiates it as an exact FIDE chess endgame solver.
</p>

<p align="center">
  <a href="paper/fixed-past-reduction.pdf"><img alt="Paper" src="https://img.shields.io/badge/paper-PDF%2C%209%20pages-1f2328"></a>
  <a href="LICENSE"><img alt="Code licence" src="https://img.shields.io/badge/code-MIT-1f2328"></a>
  <img alt="Paper licence" src="https://img.shields.io/badge/paper-CC%20BY%204.0-1f2328">
  <img alt="Verification" src="https://img.shields.io/badge/queries%20checked-850%20M-1f2328">
  <img alt="Syzygy" src="https://img.shields.io/badge/Syzygy%20disagreements-0-1f2328">
</p>

---

## The result

Take a finite deterministic two-player game with count-triggered neutral draw rules (claimable at `r` occurrences, automatic at `a`), a monotone move clock (claimable at `C`, automatic at `H`) and exactly valued exits. Ask for the win/draw/loss value of a position given an **arbitrary supplied past**.

That past enters the answer only through two frozen sets of positions:

| set | positions the past has brought to |
|---|---|
| `B` | within one occurrence of a claimable draw, `c >= r-1` |
| `A` | within one occurrence of an automatic draw, `c >= a-1` |

Nothing is counted during the solve. Under alternating ownership `B` alone suffices once the root's own status is checked.

The proof identifies the latest winning clock at each position with the **attractor rank of a reachability game**. Three things follow.

- A winning strategy positional in the position alone, which never revisits a position, so no repetition event can arise at all, including a defender's claim before a repeating move.
- A bucket algorithm linear in the arena size plus the clock bound.
- A locally checkable certificate.

Machine-checked counterexamples show that neutrality of repetition, monotonicity of the clock and alternation are each necessary.

## Evidence

**Abstract model.** Two independently written implementations, one from the paper's definitions and one from the reduction, over exhaustively enumerated arenas.

| run | arenas | root queries | mismatches |
|---|---:|---:|---:|
| two-key exhaustive, `(r,a,C,H) = (2,3,2,3)` | 4,489 | 323,208 | 0 |
| two-key exhaustive, `(3,5,4,6)` | 4,489 | 1,571,150 | 0 |
| random, 1 to 9 keys | 6,000 | 295,265 | 0 |
| dense random, 3 to 6 keys | 40,000 | 1,257,754 | 0 |
| three-key exhaustive, `(2,3,2,3)` | 300,763 | 93,083,904 | 0 |
| three-key exhaustive, `(3,5,4,6)` | 300,763 | 754,152,000 | 0 |

The propositions that go beyond the theorem were executed too: the bucket computation against synchronous iteration (345,252 deadline vectors), the certificate (2,486,548 single-entry mutations, every one rejected), the path-clock budget identity (17,884 queries, exhaustive policy enumeration), the labelled-encoding lift (20,000 encoded arenas) and the arrival-scoring game (258,455 queries). All zero mismatches, output in `abstract/results/props.json`.

**FIDE chess.** An exact solver for every pawnless three- and four-piece material under the real rules, `r = 3`, `a = 5`, `C = 100`, `H = 150` in plies.

| check | scope | result |
|---|---|---|
| Syzygy cross-check | 7,608,334 positions | 0 disagreements on win/draw/loss |
| deadline against distance to zeroing | 52,200 positions by playout | deadline = 100 minus plies to zeroing, or 149 on an immediate capture or mate |
| fragility, won positions with a single winning quiet move | 1,602,200 four-piece positions | 2.8% |

Every three-piece position was compared, and a uniform sample of 300,000 per four-piece material.

## Layout

```
paper/      fixed-past-reduction.pdf and its IEEEtran source main.tex
            fixed-past-note.pdf, a short companion note
abstract/   clean-room Python solvers for the abstract model and the property checks
            results/   JSON output of every run reported in the paper
chess/      C++ solver for pawnless materials, Syzygy comparison, playout and fragility checks
            tables/    JSON summaries, run log and the generated table fragments
```

## Reproduce

**Abstract model.** Python 3.10 or later, standard library only.

```bash
cd abstract
python run_exhaustive.py          # two-key families and random arenas, minutes
python redteam_dense.py 40000     # dense random arenas
python run_threekey.py            # three-key families, hours, resumable
python check_props.py             # property checks, seconds
```

`model.py` implements, from the paper's definitions alone, the explicit-history game (`explicit_value`), the deadline operator of Eq. (1) on frozen masks (`deadline_vector`, `fixed_past_value`), a clock-layer backward solver (`clock_layer_value`) and the one-mask variant (`one_mask_value`). Theorem 1 says the first two agree on every query. `variants.py` holds the counterexamples of Section VI.

**Chess.** Needs `python-chess` and the Syzygy 3-4-5 piece WDL and DTZ tables.

```bash
cd chess
g++ -O3 -std=c++17 -fopenmp solver.cpp -o solver
./solver KQvK tables                                    # three-piece materials first, then four-piece
python syzygy_check.py  KQvKR tables /path/to/syzygy 300000
python playout_check.py KQvKR tables 3000
python fragility.py     KQvKR tables 100000
python make_tables.py                                   # regenerates the table fragments in tables/
```

`solver.cpp` runs the deadline operator on chess keys, piece squares and side to move, for positions without castling rights. Captures are exits into the lower-material table, terminals are checkmate and stalemate. Masks can be supplied as key lists; the fresh-history case has empty masks.

The solved tables, `*.dl`, 33 MB to 168 MB per material, are not in the repository. The solver regenerates all of them in about an hour on an eight-core desktop.

## Citation

> M. Jannat, "Fixed-Past Threshold Reduction for Finite Games with Repetition Rules, with an Exact Instantiation for FIDE Chess", preprint, September 2026.

Machine-readable form in [`CITATION.cff`](CITATION.cff). The code is MIT, the paper CC BY 4.0.
