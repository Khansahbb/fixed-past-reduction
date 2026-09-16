// Exact pawnless endgame solver with FIDE repetition and move-clock semantics,
// implemented as the integer deadline operator of the fixed-past theorem.
//
// Model (paper Sections III-V and VIII):
//   key   = (piece squares, side to move); pawnless, positions without castling rights; no en passant
//   quiet = non-capturing legal move (clock +1)
//   exit  = capture (clock and history reset; value = fresh query in the lower-material table)
//   rules = claim thresholds r=3 (repetition), C=100 (halfmoves); automatic a=5, H=150
//   D_P(q) = largest clock at which target P forces a win; -1 if none.
//   Frozen masks A (auto) and B (claim) can be supplied as key lists; default empty (fresh history).
//
// Build:  g++ -O3 -std=c++17 -fopenmp solver.cpp -o solver
// Usage:  solver <material> <outdir> [mask-file]
//   material like "KQvKR" (white pieces before v, black after; kings first)
//   writes <outdir>/<material>.dl : header + int16 D_white[] + int16 D_black[] + uint8 legal[]
//   prints summary JSON (counts of win/draw/loss for each side to move, rounds, time).
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <vector>
#include <string>
#include <algorithm>
#include <chrono>
#include <map>
#include <fstream>
#ifdef _OPENMP
#include <omp.h>
#endif

static const int H = 150, C = 100;          // halfmove thresholds
static const int16_t NONE = -1;

enum PT { KING = 0, QUEEN, ROOK, BISHOP, KNIGHT };
static const char PCH[] = "KQRBN";

struct Piece { int color; int type; };      // color 0 = white, 1 = black
struct Material {
    std::vector<Piece> pcs;                 // fixed order: white king, white others, black king, black others
    std::string name;
};

static Material parse_material(const std::string& s) {
    Material m; m.name = s;
    size_t v = s.find('v');
    std::string w = s.substr(0, v), b = s.substr(v + 1);
    auto add = [&](const std::string& part, int color) {
        for (char ch : part) {
            const char* p = strchr(PCH, ch); if (!p) { fprintf(stderr, "bad piece %c\n", ch); exit(1); }
            m.pcs.push_back({color, int(p - PCH)});
        }
    };
    add(w, 0); add(b, 1);
    return m;
}

static inline int sq_file(int s) { return s & 7; }
static inline int sq_rank(int s) { return s >> 3; }
static inline bool king_adjacent(int a, int b) {
    return std::abs(sq_file(a) - sq_file(b)) <= 1 && std::abs(sq_rank(a) - sq_rank(b)) <= 1;
}

// ---- attack tables ----
static uint64_t KN_ATT[64], KG_ATT[64];
static void init_tables() {
    for (int s = 0; s < 64; s++) {
        int f = sq_file(s), r = sq_rank(s); uint64_t kn = 0, kg = 0;
        const int kd[8][2] = {{1,2},{2,1},{-1,2},{-2,1},{1,-2},{2,-1},{-1,-2},{-2,-1}};
        for (auto& d : kd) { int ff = f + d[0], rr = r + d[1]; if (ff >= 0 && ff < 8 && rr >= 0 && rr < 8) kn |= 1ULL << (rr * 8 + ff); }
        for (int df = -1; df <= 1; df++) for (int dr = -1; dr <= 1; dr++) {
            if (!df && !dr) continue; int ff = f + df, rr = r + dr;
            if (ff >= 0 && ff < 8 && rr >= 0 && rr < 8) kg |= 1ULL << (rr * 8 + ff);
        }
        KN_ATT[s] = kn; KG_ATT[s] = kg;
    }
}
static uint64_t slide_att(int s, uint64_t occ, bool rook, bool bishop) {
    uint64_t a = 0; int f = sq_file(s), r = sq_rank(s);
    const int rd[4][2] = {{1,0},{-1,0},{0,1},{0,-1}}, bd[4][2] = {{1,1},{1,-1},{-1,1},{-1,-1}};
    auto run = [&](const int d[2]) {
        int ff = f + d[0], rr = r + d[1];
        while (ff >= 0 && ff < 8 && rr >= 0 && rr < 8) {
            int t = rr * 8 + ff; a |= 1ULL << t; if (occ & (1ULL << t)) break; ff += d[0]; rr += d[1];
        }
    };
    if (rook) for (auto& d : rd) run(d);
    if (bishop) for (auto& d : bd) run(d);
    return a;
}
static uint64_t piece_att(int type, int s, uint64_t occ) {
    switch (type) {
        case KING: return KG_ATT[s];
        case KNIGHT: return KN_ATT[s];
        case QUEEN: return slide_att(s, occ, true, true);
        case ROOK: return slide_att(s, occ, true, false);
        case BISHOP: return slide_att(s, occ, false, true);
    }
    return 0;
}

// ---- position encoding ----
struct Table {
    Material mat;
    int n;                                  // number of pieces
    size_t nkeys;                           // 2 * 64^n
    std::vector<uint8_t> legal;             // 1 if legal key
    std::vector<int16_t> D[2];              // deadline per target player
    size_t index(const int* sq, int stm) const {
        size_t idx = 0; for (int i = 0; i < n; i++) idx = idx * 64 + sq[i]; return idx * 2 + stm;
    }
    void decode(size_t idx, int* sq, int& stm) const {
        stm = idx & 1; idx >>= 1; for (int i = n - 1; i >= 0; i--) { sq[i] = idx & 63; idx >>= 6; }
    }
};

static bool attacked(const Table& T, const int* sq, int target_sq, int by_color, uint64_t occ) {
    for (int i = 0; i < T.n; i++) if (T.mat.pcs[i].color == by_color && (piece_att(T.mat.pcs[i].type, sq[i], occ) & (1ULL << target_sq))) return true;
    return false;
}
static int king_of(const Table& T, int color) { for (int i = 0; i < T.n; i++) if (T.mat.pcs[i].color == color && T.mat.pcs[i].type == KING) return i; return -1; }

static bool is_legal_key(const Table& T, const int* sq, int stm) {
    for (int i = 0; i < T.n; i++) for (int j = i + 1; j < T.n; j++) if (sq[i] == sq[j]) return false;
    int wk = king_of(T, 0), bk = king_of(T, 1);
    if (king_adjacent(sq[wk], sq[bk])) return false;
    uint64_t occ = 0; for (int i = 0; i < T.n; i++) occ |= 1ULL << sq[i];
    int other = 1 - stm; int ok = king_of(T, other);
    if (attacked(T, sq, sq[ok], stm, occ)) return false;         // side not to move in check: illegal
    return true;
}

// Boundary lookup for captures: map material name -> table (already solved, fresh masks)
static std::map<std::string, Table*> SOLVED;

static std::string material_name(const std::vector<Piece>& pcs) {
    std::string w, b; for (auto& p : pcs) (p.color ? b : w) += PCH[p.type]; return w + "v" + b;
}

struct MoveOut { size_t to_idx; bool capture; int16_t exit_val[2]; };

// Generate legal moves from key; for captures compute exit value per target via lower table.
static void gen_moves(const Table& T, const int* sq, int stm, std::vector<MoveOut>& out, bool& in_check) {
    out.clear();
    uint64_t occ = 0; for (int i = 0; i < T.n; i++) occ |= 1ULL << sq[i];
    int myk = king_of(T, stm);
    in_check = attacked(T, sq, sq[myk], 1 - stm, occ);
    int nsq[4];
    for (int i = 0; i < T.n; i++) {
        if (T.mat.pcs[i].color != stm) continue;
        uint64_t att = piece_att(T.mat.pcs[i].type, sq[i], occ);
        while (att) {
            int t = __builtin_ctzll(att); att &= att - 1;
            int captured = -1;
            for (int j = 0; j < T.n; j++) if (sq[j] == t) { captured = j; break; }
            if (captured >= 0 && T.mat.pcs[captured].color == stm) continue;         // own piece
            if (captured >= 0 && T.mat.pcs[captured].type == KING) continue;         // cannot happen in legal keys
            memcpy(nsq, sq, sizeof(int) * T.n); nsq[i] = t;
            // legality: own king not attacked after move
            uint64_t nocc = 0; for (int k = 0; k < T.n; k++) if (k != captured) nocc |= 1ULL << nsq[k];
            bool bad = false;
            for (int k = 0; k < T.n; k++) {
                if (k == captured || T.mat.pcs[k].color == stm) continue;
                if (piece_att(T.mat.pcs[k].type, nsq[k], nocc) & (1ULL << nsq[myk])) { bad = true; break; }
            }
            if (bad) continue;
            MoveOut m; m.capture = captured >= 0;
            if (!m.capture) { m.to_idx = T.index(nsq, 1 - stm); m.exit_val[0] = m.exit_val[1] = 0; }
            else {
                std::vector<Piece> rem; int rsq[4]; int c = 0;
                for (int k = 0; k < T.n; k++) if (k != captured) { rem.push_back(T.mat.pcs[k]); rsq[c++] = nsq[k]; }
                std::string nm = material_name(rem);
                auto it = SOLVED.find(nm);
                if (it == SOLVED.end()) {                 // bare kings or unknown: draw
                    m.exit_val[0] = m.exit_val[1] = NONE; m.to_idx = 0;
                } else {
                    Table* L = it->second; size_t li = L->index(rsq, 1 - stm);
                    for (int P = 0; P < 2; P++) m.exit_val[P] = (L->D[P][li] >= 0) ? int16_t(H - 1) : NONE;  // fresh query at clock 0
                    m.to_idx = 0;
                }
            }
            out.push_back(m);
        }
    }
}

struct Masks { std::vector<uint8_t> A, B; bool any = false; };

static void solve(Table& T, const Masks& M, int& rounds, double& secs) {
    auto t0 = std::chrono::steady_clock::now();
    T.nkeys = size_t(2) << (6 * T.n);
    T.legal.assign(T.nkeys, 0);
    for (int P = 0; P < 2; P++) T.D[P].assign(T.nkeys, NONE);
    // terminal classification stored in a small array: 0 nonterminal, 1 mate (stm loses), 2 stalemate
    std::vector<uint8_t> term(T.nkeys, 0);
    #pragma omp parallel for schedule(static)
    for (long long idx = 0; idx < (long long)T.nkeys; idx++) {
        int sq[4], stm; T.decode(idx, sq, stm);
        if (!is_legal_key(T, sq, stm)) continue;
        T.legal[idx] = 1;
        std::vector<MoveOut> mv; bool chk; gen_moves(T, sq, stm, mv, chk);
        if (mv.empty()) { term[idx] = chk ? 1 : 2; if (chk) { T.D[1 - stm][idx] = H; } }
    }
    rounds = 0; bool changed = true;
    while (changed) {
        changed = false; rounds++;
        long long nchg = 0;
        #pragma omp parallel for schedule(dynamic, 4096) reduction(+:nchg)
        for (long long idx = 0; idx < (long long)T.nkeys; idx++) {
            if (!T.legal[idx] || term[idx]) continue;
            int sq[4], stm; T.decode(idx, sq, stm);
            std::vector<MoveOut> mv; bool chk; gen_moves(T, sq, stm, mv, chk);
            bool hasQuiet = false; for (auto& m : mv) if (!m.capture) { hasQuiet = true; break; }
            for (int P = 0; P < 2; P++) {
                int16_t cur = T.D[P][idx];
                int16_t val;
                if (M.any && M.A[idx]) { val = NONE; }
                else if (stm != P && M.any && (M.B[idx] || [&]{ for (auto& m : mv) if (!m.capture && M.B[m.to_idx]) return true; return false; }())) { val = NONE; }
                else {
                    int K = (stm == P) ? H - 1 : std::min(H - 1, C - 1 - (hasQuiet ? 1 : 0));
                    int agg = (stm == P) ? -1 : H;
                    for (auto& m : mv) {
                        int w = m.capture ? m.exit_val[P] : std::max(-1, int(T.D[P][m.to_idx]) - 1);
                        if (stm == P) agg = std::max(agg, w); else agg = std::min(agg, w);
                    }
                    val = int16_t(std::min(K, agg));
                }
                if (val != cur) { T.D[P][idx] = val; nchg++; }
            }
        }
        if (nchg) changed = true;
    }
    secs = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
}

static void write_table(const Table& T, const std::string& path) {
    std::ofstream f(path, std::ios::binary);
    char hdr[16] = {0}; strncpy(hdr, T.mat.name.c_str(), 15); f.write(hdr, 16);
    uint32_t n = T.n; f.write((char*)&n, 4);
    for (int P = 0; P < 2; P++) f.write((char*)T.D[P].data(), T.D[P].size() * 2);
    f.write((char*)T.legal.data(), T.legal.size());
}
static bool read_table(Table& T, const std::string& path) {
    std::ifstream f(path, std::ios::binary); if (!f) return false;
    char hdr[16]; f.read(hdr, 16); uint32_t n; f.read((char*)&n, 4);
    T.n = n; T.nkeys = size_t(2) << (6 * n);
    for (int P = 0; P < 2; P++) { T.D[P].resize(T.nkeys); f.read((char*)T.D[P].data(), T.nkeys * 2); }
    T.legal.resize(T.nkeys); f.read((char*)T.legal.data(), T.nkeys);
    return true;
}

// Load all lower-material tables needed (every single-capture reduction of mat) from outdir.
static void load_boundaries(const Material& mat, const std::string& outdir) {
    for (size_t i = 0; i < mat.pcs.size(); i++) {
        if (mat.pcs[i].type == KING) continue;
        std::vector<Piece> rem; for (size_t k = 0; k < mat.pcs.size(); k++) if (k != i) rem.push_back(mat.pcs[k]);
        std::string nm = material_name(rem);
        if (nm == "KvK" || SOLVED.count(nm)) continue;
        Table* L = new Table(); L->mat = parse_material(nm);
        if (!read_table(*L, outdir + "/" + nm + ".dl")) { fprintf(stderr, "missing boundary table %s (solve it first)\n", nm.c_str()); exit(2); }
        SOLVED[nm] = L;
    }
}

int main(int argc, char** argv) {
    if (argc < 3) { fprintf(stderr, "usage: solver <material> <outdir> [maskfile]\n"); return 1; }
    init_tables();
    std::string matname = argv[1], outdir = argv[2];
    Table T; T.mat = parse_material(matname); T.n = T.mat.pcs.size();
    if (T.n > 4) { fprintf(stderr, "max 4 pieces\n"); return 1; }
    load_boundaries(T.mat, outdir);
    Masks M;
    if (argc >= 4) {
        M.any = true; size_t nk = size_t(2) << (6 * T.n); M.A.assign(nk, 0); M.B.assign(nk, 0);
        std::ifstream mf(argv[3]); std::string kind; long long idx;
        while (mf >> kind >> idx) { if (kind == "A") { M.A[idx] = 1; M.B[idx] = 1; } else M.B[idx] = 1; }
    }
    int rounds; double secs; solve(T, M, rounds, secs);
    // summary from side-to-move perspective
    long long legal = 0, w[2] = {0, 0}, l[2] = {0, 0}, d[2] = {0, 0};
    for (size_t idx = 0; idx < T.nkeys; idx++) {
        if (!T.legal[idx]) continue; legal++; int stm = idx & 1;
        bool mw = T.D[stm][idx] >= 0, ml = T.D[1 - stm][idx] >= 0;
        if (mw) w[stm]++; else if (ml) l[stm]++; else d[stm]++;
    }
    if (!M.any) write_table(T, outdir + "/" + matname + ".dl");
    printf("{\"material\":\"%s\",\"legal\":%lld,\"wtm\":{\"win\":%lld,\"draw\":%lld,\"loss\":%lld},\"btm\":{\"win\":%lld,\"draw\":%lld,\"loss\":%lld},\"rounds\":%d,\"seconds\":%.1f,\"masked\":%s}\n",
        matname.c_str(), legal, w[0], d[0], l[0], w[1], d[1], l[1], rounds, secs, M.any ? "true" : "false");
    return 0;
}
