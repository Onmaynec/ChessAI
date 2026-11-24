#pragma once
#include "chess.hpp"
#include <cstdint>
#include <optional>

namespace chess {
struct SearchResult {
    std::optional<Move> best;
    int score_cp=0;
    uint64_t nodes=0;
};
// Deterministic, hand-crafted alpha-beta BASELINE. No neural network in v0.1.0.
SearchResult search_baseline(const Position& position, int depth);
}
