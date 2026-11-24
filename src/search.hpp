#pragma once
#include "chess.hpp"
#include <cstdint>
#include <optional>
#include <vector>

namespace chess {
struct SearchResult {
    std::optional<Move> best;
    int score_cp=0;
    uint64_t nodes=0;
    int completed_depth=0;
    uint64_t qnodes=0, tt_hits=0;
    uint64_t elapsed_ms=0;
    bool stopped=false;
    std::vector<Move> pv;
};
// Deterministic, hand-crafted alpha-beta BASELINE. No neural network in v0.1.0.
SearchResult search_baseline(const Position& position, int depth);

struct SearchLimits {
    int depth=3;             // maximum completed full-width depth, 1..12
    uint64_t nodes=0;        // 0 = no node limit
    uint64_t movetime_ms=0;  // 0 = no wall-clock limit
    unsigned hash_mb=16;     // bounded local table; 0 disables it
    bool quiescence=true;
};
// prior_keys excludes the current position; use chess::repetition_key strings.
SearchResult search_deep(const Position& position, const SearchLimits& limits={},
                         const std::vector<std::string>& prior_keys={});
int evaluate_deep(const Position& position);
}
