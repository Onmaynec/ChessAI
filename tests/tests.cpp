#include "chess.hpp"
#include "search.hpp"
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
using namespace chess;
namespace {
int assertions=0;
void check(bool c,const std::string& what){++assertions;if(!c)throw std::runtime_error("FAIL: "+what);}
void perft_case(const std::string& fen,std::vector<uint64_t> counts) {
    auto p=parse_fen(fen);
    for(size_t i=0;i<counts.size();++i){auto n=perft(p,int(i+1));check(n==counts[i],"perft depth="+std::to_string(i+1)+" FEN="+fen+" expected="+std::to_string(counts[i])+" got="+std::to_string(n));}
}
bool has(const Position& p,const std::string& move){for(const Move& m:legal_moves(p))if(uci(m)==move)return true;return false;}
void invalid(const std::string& fen){bool threw=false;try{parse_fen(fen);}catch(const std::exception&){threw=true;}check(threw,"invalid FEN must throw: "+fen);}
}
int main(){
    try {
        perft_case(std::string(START_FEN),{20,400,8902,197281});
        perft_case("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",{48,2039,97862});
        perft_case("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",{14,191,2812,43238});
        perft_case("rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",{44,1486,62379});
        auto p=parse_fen(std::string(START_FEN));
        check(to_fen(p)==START_FEN,"starting FEN round-trip");
        check(!apply_uci(p,"e2e5"),"illegal move rejected");
        check(apply_uci(p,"e2e4"),"e2e4 legal");
        check(p.en_passant==text_to_square("e3"),"double pawn creates en-passant target");
        check(p.halfmove==0 && p.turn==-1,"pawn clock/turn");
        check(to_fen(parse_fen(to_fen(p)))==to_fen(p),"FEN after move round-trip");
        check(apply_uci(p,"e7e5"),"e7e5 legal");
        check(p.fullmove==2,"fullmove advances after black");
        auto ep=parse_fen("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1");
        check(has(ep,"e5d6"),"en passant legal");
        check(apply_uci(ep,"e5d6"),"en passant executed");
        check(ep.board[text_to_square("d5")]==EMPTY && ep.board[text_to_square("d6")]==PAWN,"en passant pawn removed");
        auto pin=parse_fen("4r1k1/8/8/3pP3/8/8/8/4K3 w - d6 0 1");
        check(!has(pin,"e5d6"),"pinned en passant is illegal");
        auto castle=parse_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1");
        check(has(castle,"e1g1") && has(castle,"e1c1"),"both castlings legal");
        check(apply_uci(castle,"e1g1"),"castle executed");
        check(castle.board[6]==KING && castle.board[5]==ROOK && castle.board[7]==EMPTY,"castling rook moves");
        check((castle.castle & 3)==0,"castling rights cleared");
        auto danger=parse_fen("4kr2/8/8/8/8/8/8/4K2R w K - 0 1");
        check(!has(danger,"e1g1"),"cannot castle through check");
        auto promo=parse_fen("4k3/P7/8/8/8/8/8/4K3 w - - 0 1");
        for(const auto& s:{"a7a8q","a7a8r","a7a8b","a7a8n"})check(has(promo,s),std::string("promotion ")+s);
        check(apply_uci(promo,"a7a8n") && promo.board[text_to_square("a8")]==KNIGHT,"knight underpromotion");
        auto mate=parse_fen("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1");
        check(outcome(mate,{}).reason=="checkmate" && outcome(mate,{}).result=="1-0","checkmate status");
        auto stale=parse_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1");
        check(outcome(stale,{}).reason=="stalemate","stalemate status");
        check(insufficient_material(parse_fen("4k3/8/8/8/8/8/8/4K3 w - - 0 1")),"K vs K is dead");
        check(!insufficient_material(parse_fen("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")),"KQ vs K is not dead");
        Position repeat=parse_fen(std::string(START_FEN));
        std::vector<std::string> keys{repetition_key(repeat)};
        for(int i=0;i<2;++i)for(const auto& s:{"g1f3","g8f6","f3g1","f6g8"}){
            check(apply_uci(repeat,s),std::string("repeat sequence move ")+s);
            keys.push_back(repetition_key(repeat));
        }
        check(outcome(repeat,keys).reason=="threefold_repetition_claimed","threefold claim policy");
        invalid("xnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1");
        invalid("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0");
        invalid("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR z KQkq - 0 1");
        invalid("4k3/8/8/4P3/8/8/8/4K3 w - d6 0 1");
        invalid("4k3/8/8/8/8/8/4R3/4K3 w - - 0 1");
        auto capture_rook=parse_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1");
        check(apply_uci(capture_rook,"a1a8"),"corner rook capture legal");
        check((capture_rook.castle&10)==0,"corner capture clears both rook castling rights");
        auto fifty=parse_fen("r3k3/8/8/8/8/8/8/R3K3 w - - 100 1");
        check(outcome(fifty,{}).reason=="50_move_rule_claimed","50-move claim policy");
        auto seventyfive=parse_fen("r3k3/8/8/8/8/8/8/R3K3 w - - 150 1");
        check(outcome(seventyfive,{}).reason=="75_move_rule","75-move auto draw");
        auto best=search_baseline(parse_fen(std::string(START_FEN)),2);
        check(best.best.has_value(),"baseline search returns a move");
        check(has(parse_fen(std::string(START_FEN)),uci(*best.best)),"baseline chooses legal move");
        std::cout<<"PASS: "<<assertions<<" assertions across perft, move legality, FEN, draws, baseline.\n";
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
