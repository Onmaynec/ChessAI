#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace chess {
constexpr std::string_view START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

enum Piece : int8_t { EMPTY=0, PAWN=1, KNIGHT=2, BISHOP=3, ROOK=4, QUEEN=5, KING=6 };
enum MoveFlag : uint8_t { NORMAL=0, EN_PASSANT=1, CASTLE=2, DOUBLE_PAWN=4 };

struct Move {
    int from=0, to=0;
    int8_t promotion=EMPTY;
    uint8_t flags=NORMAL;
    bool operator==(const Move& o) const {
        return from==o.from && to==o.to && promotion==o.promotion;
    }
};

struct Position {
    std::array<int8_t,64> board{};
    int8_t turn=1;              // white +1, black -1
    uint8_t castle=0;           // K=1 Q=2 k=4 q=8
    int8_t en_passant=-1;       // target square, not captured pawn
    uint16_t halfmove=0;
    uint16_t fullmove=1;
};

Position parse_fen(const std::string& fen);
std::string to_fen(const Position& p);
std::string square_to_text(int square);
int text_to_square(std::string_view text);
std::string uci(const Move& m);
std::vector<Move> legal_moves(const Position& p);
bool is_square_attacked(const Position& p, int square, int by_color);
bool in_check(const Position& p, int color);
Position make_move(const Position& p, const Move& m);
bool apply_uci(Position& p, const std::string& text);
uint64_t perft(const Position& p, int depth);
std::string repetition_key(const Position& p);
bool insufficient_material(const Position& p);

struct Outcome {
    // result: "1-0", "0-1", "1/2-1/2", "*"
    std::string result="*";
    std::string reason="ongoing";
    bool finished=false;
};
Outcome outcome(const Position& p, const std::vector<std::string>& position_keys);
std::string board_ascii(const Position& p);
}
