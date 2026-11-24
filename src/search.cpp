#include "search.hpp"
#include <algorithm>
#include <array>
#include <cmath>

namespace chess {
namespace {
constexpr int MATE=30000;
constexpr std::array<int,7> VALUES{{0,100,320,330,500,900,0}};
int evaluate(const Position& p) {
    int result=0;
    for(int s=0;s<64;++s) {
        const int pc=p.board[s];if(!pc)continue;
        const int side=pc>0?1:-1,kind=std::abs(pc),f=s%8,r=s/8;
        int bonus=0;
        if(kind==PAWN)bonus=3*(side==1?r:7-r);
        if(kind==KNIGHT||kind==BISHOP)bonus=3*(3-std::abs(f-3))+3*(3-std::abs(r-3));
        if(kind==KING)bonus=0;
        result+=side*(VALUES[kind]+bonus);
    }
    return p.turn*result;
}
int priority(const Position& p, const Move& m) {
    const int victim=std::abs(p.board[m.to]);
    return (victim ? 20*VALUES[victim]-VALUES[std::abs(p.board[m.from])] : 0)
        +(m.flags&EN_PASSANT?2000:0)+(m.promotion?VALUES[m.promotion]*2:0);
}
int negamax(const Position& p,int depth,int alpha,int beta,int ply,uint64_t& nodes) {
    ++nodes;
    if(p.halfmove>=100 || insufficient_material(p))return 0;
    auto moves=legal_moves(p);
    if(moves.empty())return in_check(p,p.turn)?-MATE+ply:0;
    if(depth==0)return evaluate(p);
    std::sort(moves.begin(),moves.end(),[&](const Move& a,const Move& b){return priority(p,a)>priority(p,b);});
    int best=-MATE-1;
    for(const Move& m:moves){
        int score=-negamax(make_move(p,m),depth-1,-beta,-alpha,ply+1,nodes);
        best=std::max(best,score);
        alpha=std::max(alpha,score);
        if(alpha>=beta)break;
    }
    return best;
}
}
SearchResult search_baseline(const Position& p,int depth) {
    SearchResult out;
    auto moves=legal_moves(p);
    if(moves.empty())return out;
    depth=std::max(1,std::min(depth,6));
    std::sort(moves.begin(),moves.end(),[&](const Move& a,const Move& b){return priority(p,a)>priority(p,b);});
    int best=-MATE-1,alpha=-MATE-1;
    for(const Move& m:moves) {
        int score=-negamax(make_move(p,m),depth-1,-MATE-1,-alpha,1,out.nodes);
        if(score>best){best=score;out.best=m;}
        alpha=std::max(alpha,score);
    }
    out.score_cp=best;
    out.completed_depth=depth;
    if(out.best)out.pv.push_back(*out.best);
    return out;
}
}
