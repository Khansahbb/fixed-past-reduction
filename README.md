# Fixed-past threshold reduction for finite games with repetition rules

Paper, source, code and results for

> M. Jannat, "Fixed-Past Threshold Reduction for Finite Games with Repetition Rules, with an Exact Instantiation for FIDE Chess", preprint, September 2026. `paper/fixed-past-reduction.pdf`

The paper proves that, for a finite deterministic two-player game with count-triggered neutral draw rules (claimable at r occurrences, automatic at a), a monotone move clock (claimable at C, automatic at H) and exactly valued exits, the win/draw/loss value of a query with an arbitrary supplied past depends on that past only through two frozen sets of positions, B = {c >= r-1} and A = {c >= a-1}, with no occurrence counting during the solve. Under alternating ownership B alone suffices after checking the root. The latest winning clock at each position is the attractor rank of a reachability game, which gives a key-positional winning strategy, a bucket algorithm linear in the arena size plus the clock bound, and a local certificate. For FIDE chess the reduction is instantiated by an exact solver for every pawnless three- and four-piece material under the repetition and move-clock rules.

## Contents

```
paper/      fixed-past-reduction.pdf and its IEEEtran source main.tex
abstract/   clean-room Python solvers for the abstract model and the property checks
            results/   JSON output of every run reported in the paper
chess/      C++ solver for pawnless materials, Syzygy comparison, playout and fragility checks
            tables/    JSON summaries, run log and the generated table fragments
```

## Abstract model (`abstract/`)

`model.py` implements, from the paper's definitions only, the explicit-history game (`explicit_value`), the deadline operator of Eq. (1) on frozen masks (`deadline_vector`, `fixed_past_value`), a clock-layer backward solver (`clock_layer_value`) and the one-mask variant (`one_mask_value`). Theorem 1 says the first two must agree on every query.

| run | arenas | root queries | mismatches |
|---|---|---|---|
| two-key exhaustive, (r,a,C,H) = (2,3,2,3) | 4,489 | 323,208 | 0 |
| two-key exhaustive, (3,5,4,6) | 4,489 | 1,571,150 | 0 |
| random, 1 to 9 keys | 6,000 | 295,265 | 0 |
| dense random, 3 to 6 keys | 40,000 | 1,257,754 | 0 |
| three-key exhaustive, (2,3,2,3) | 300,763 | 93,083,904 | 0 |
| three-key exhaustive, (3,5,4,6) | 300,763 | 754,152,000 | 0 |

`check_props.py` executes the propositions that go beyond the theorem: the bucket computation against synchronous iteration (345,252 deadline vectors), the certificate (2,486,548 single-entry mutations, all rejected), the path-clock budget identity (17,884 queries, exhaustive policy enumeration), the labelled-encoding lift (20,000 encoded arenas) and the arrival-scoring game (258,455 queries on alternating arenas). All zero mismatches; output in `results/props.json`. `variants.py` holds the counterexamples of Section VI.

```
cd abstract
python run_exhaustive.py          # two-key families and random arenas, minutes
python redteam_dense.py 40000     # dense random arenas
python run_threekey.py            # three-key families, hours; resumable
python check_props.py             # property checks, seconds
```

Python 3.10 or later, standard library only.

## Chess (`chess/`)

`solver.cpp` implements the deadline operator on chess keys (piece squares and side to move, positions without castling rights) for every pawnless material with up to four pieces. Captures are exits into the lower-material table, terminals are checkmate and stalemate, thresholds are r = 3, a = 5, C = 100, H = 150 in plies. Masks can be supplied as key lists; the fresh-history case has empty masks.

```
cd chess
g++ -O3 -std=c++17 -fopenmp solver.cpp -o solver
./solver KQvK tables            # three-piece materials first, then four-piece
python syzygy_check.py KQvKR tables /path/to/syzygy 300000
python playout_check.py KQvKR tables 3000
python fragility.py KQvKR tables 100000
python make_tables.py           # regenerates the table fragments in tables/
```

Checks need `python-chess` and the Syzygy 3-4-5 piece WDL and DTZ tables. Every three-piece position and a uniform sample of 300,000 positions per four-piece material were compared with Syzygy: 7,608,334 positions, 0 disagreements on win/draw/loss. On winning positions the deadline equals 100 minus the exact number of plies to zeroing, or 149 when the winning move captures or mates, verified by playout on 52,200 positions. Fragility, the share of won positions with a single winning quiet move, is 2.8% over 1,602,200 sampled four-piece positions.

The solved tables (`*.dl`, 33 MB to 168 MB per material) are not included; the solver regenerates all of them in about an hour on an eight-core desktop.

## Licence and citation

The code is released under the MIT licence and the paper under CC BY 4.0. Cite with `CITATION.cff`.
