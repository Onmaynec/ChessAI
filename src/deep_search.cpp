#include "search.hpp"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <vector>

namespace chess {
namespace {
constexpr int MATE=30000, INF=32000, MATE_BOUND=29000, MAX_PLY=64;
constexpr int QUIET_Q_LIMIT=8, CHECK_Q_LIMIT=24;
constexpr std::array<int,7> V{{0,100,320,335,500,900,0}};
constexpr int knight_steps[8][2]={{1,2},{2,1},{-1,2},{-2,1},{1,-2},{2,-1},{-1,-2},{-2,-1}};
constexpr int rays[8][2]={{1,0},{-1,0},{0,1},{0,-1},{1,1},{-1,1},{1,-1},{-1,-1}};
bool inside(int f,int r){return f>=0&&f<8&&r>=0&&r<8;}
int center(int f,int r){return 14-std::abs(2*f-7)-std::abs(2*r-7);}
bool tactical(const Position& p,const Move& m){return p.board[m.to]!=EMPTY || (m.flags&EN_PASSANT) || m.promotion!=EMPTY;}

uint64_t mix(uint64_t x){
    x+=0x9e3779b97f4a7c15ULL;
    x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;
    x=(x^(x>>27))*0x94d049bb133111ebULL;
    return x^(x>>31);
}
// Zobrist XOR of fixed pseudo-random piece/square and rights keys.
// repetition_key canonicalizes uncapturable en-passant rights.
uint64_t zobrist(const std::string& key){
    uint64_t h=0;
    for(size_t i=0;i<key.size();++i)
        h^=mix(0x43484553534149ULL+i*256+static_cast<unsigned char>(key[i]));
    return h;
}

int pseudo_mobility(const Position& p,int sq,int color,int kind){
    int count=0,f=sq%8,r=sq/8;
    if(kind==KNIGHT){
        for(const auto& d:knight_steps){
            int x=f+d[0],y=r+d[1];
            if(inside(x,y)&&p.board[y*8+x]*color<=0)++count;
        }
    }else if(kind==BISHOP||kind==ROOK||kind==QUEEN){
        for(int i=0;i<8;++i){
            if((kind==BISHOP&&i<4)||(kind==ROOK&&i>=4))continue;
            int x=f+rays[i][0],y=r+rays[i][1];
            while(inside(x,y)){
                int target=p.board[y*8+x]*color;
                if(target>0)break;
                ++count;
                if(target<0)break;
                x+=rays[i][0];y+=rays[i][1];
            }
        }
    }
    return count;
}

int evaluate_position(const Position& p){
    int material[2]{}, bishops[2]{}, kings[2]{-1,-1}, pawn_files[2][8]{};
    int phase=0;
    for(int s=0;s<64;++s){
        int pc=p.board[s];if(!pc)continue;
        int c=pc>0?0:1,k=std::abs(pc);
        material[c]+=V[k];
        if(k==PAWN)++pawn_files[c][s%8];
        if(k==BISHOP)++bishops[c];
        if(k==KING)kings[c]=s;
        phase+=(k==QUEEN?4:k==ROOK?2:k==BISHOP||k==KNIGHT?1:0);
    }
    phase=std::min(24,phase);
    int score[2]{material[0],material[1]};
    for(int c=0;c<2;++c){
        if(bishops[c]>=2)score[c]+=25;
        for(int f=0;f<8;++f){
            int n=pawn_files[c][f];
            if(n>1)score[c]-=12*(n-1);
            if(n && !(f>0&&pawn_files[c][f-1]) && !(f<7&&pawn_files[c][f+1]))score[c]-=10*n;
        }
    }
    for(int s=0;s<64;++s){
        const int pc=p.board[s];if(!pc)continue;
        int c=pc>0?0:1,color=pc>0?1:-1,k=std::abs(pc),f=s%8,r=s/8,advance=color==1?r:7-r;
        int cent=center(f,r);
        if(k==PAWN){
            score[c]+=advance*3+cent;
            bool passed=true;
            for(int x=std::max(0,f-1);x<=std::min(7,f+1);++x)
                for(int y=r+color;y>=0&&y<8;y+=color)
                    if(p.board[y*8+x]==-color*PAWN)passed=false;
            if(passed)score[c]+=advance*advance*(48-phase)/24;
            for(int x:{f-1,f+1})if(inside(x,r-color)&&p.board[(r-color)*8+x]==color*PAWN)score[c]+=6;
        }else if(k==KNIGHT||k==BISHOP||k==ROOK||k==QUEEN){
            if(k==KNIGHT)score[c]+=3*cent;
            if(k==BISHOP)score[c]+=2*cent;
            score[c]+=pseudo_mobility(p,s,color,k)*(k==QUEEN?1:2);
            if(k==ROOK){
                if(!pawn_files[c][f])score[c]+=pawn_files[1-c][f]?10:18;
                if(advance==6)score[c]+=12;
            }
        }else if(k==KING){
            int shield=0;
            for(int x=std::max(0,f-1);x<=std::min(7,f+1);++x){
                if(inside(x,r+color)&&p.board[(r+color)*8+x]==color*PAWN)shield+=10;
                if(inside(x,r+2*color)&&p.board[(r+2*color)*8+x]==color*PAWN)shield+=4;
            }
            int danger=0;
            if(phase>=8){
                for(const auto& d:rays){
                    int x=f+d[0],y=r+d[1];
                    if(inside(x,y)&&is_square_attacked(p,y*8+x,-color))danger+=6;
                }
                if(in_check(p,color))danger+=12;
            }
            score[c]+=((shield-danger-cent)*phase + 4*cent*(24-phase))/24;
        }
    }
    // Reward driving the weaker king to the edge in clearly winning low-material endings.
    if(phase<=4 && kings[0]>=0 && kings[1]>=0){
        int diff=material[0]-material[1];
        if(std::abs(diff)>=450){
            int strong=diff>0?0:1,weak=1-strong;
            int s=kings[strong],w=kings[weak];
            int distance=std::max(std::abs(s%8-w%8),std::abs(s/8-w/8));
            score[strong]+=3*(14-center(w%8,w/8))+5*(7-distance);
        }
    }
    return std::clamp(p.turn*(score[0]-score[1])+8,-MATE_BOUND+1,MATE_BOUND-1);
}

struct AbortSearch {};
enum Bound : uint8_t { EXACT, LOWER, UPPER };
struct Entry {
    uint64_t board=0, context=0;
    Move move{};
    int score=0, depth=-1;
    Bound bound=EXACT;
};
int pack_mate(int score,int ply){
    return score>=MATE_BOUND?score+ply:score<=-MATE_BOUND?score-ply:score;
}
int unpack_mate(int score,int ply){
    return score>=MATE_BOUND?score-ply:score<=-MATE_BOUND?score+ply:score;
}
struct Searcher {
    SearchLimits limits;
    SearchResult result;
    std::chrono::steady_clock::time_point start=std::chrono::steady_clock::now();
    std::vector<Entry> table;
    std::vector<uint64_t> history;
    std::array<std::array<std::optional<Move>,2>,MAX_PLY> killers{};
    int history_score[2][64][64]{};
    std::array<std::vector<Move>,MAX_PLY> pv{};

    Searcher(const SearchLimits& options,const std::vector<std::string>& prior):limits(options){
        unsigned mb=std::min(256u,limits.hash_mb);
        if(mb)table.resize(std::max<size_t>(1,static_cast<size_t>(mb)*1024*1024/sizeof(Entry)));
        for(const auto& key:prior)history.push_back(zobrist(key));
    }
    uint64_t elapsed() const {
        return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
                   std::chrono::steady_clock::now()-start).count());
    }
    void tick(bool q){
        if((limits.nodes&&result.nodes>=limits.nodes) ||
           (limits.movetime_ms&&elapsed()>=limits.movetime_ms))throw AbortSearch{};
        ++result.nodes;
        if(q)++result.qnodes;
    }
    // Count the current position, restricted to the available reversible history.
    size_t history_begin(const Position& p) const {
        size_t keep=static_cast<size_t>(p.halfmove)+1;
        return history.size()>keep?history.size()-keep:0;
    }
    bool draw(const Position& p,uint64_t key) const{
        if(p.halfmove>=100||insufficient_material(p))return true;
        int repeats=0;
        for(size_t i=history_begin(p);i<history.size();++i)
            if(history[i]==key&&++repeats>=3)return true;
        return false;
    }
    uint64_t context(const Position& p) const{
        // Bounds are usable only with compatible halfmove and repetition history.
        // Sum, rather than XOR, preserves multiplicities; order is immaterial.
        uint64_t h=mix(static_cast<uint64_t>(p.halfmove)+0x9176ULL);
        for(size_t i=history_begin(p);i<history.size();++i)h+=mix(history[i]);
        return h;
    }
    struct Scope {
        std::vector<uint64_t>& path;
        explicit Scope(std::vector<uint64_t>& p,uint64_t key):path(p){path.push_back(key);}
        ~Scope(){path.pop_back();}
    };
    int priority(const Position& p,const Move& m,const std::optional<Move>& tt,int ply) const{
        if(tt&&m==*tt)return 1000000;
        if(tactical(p,m)){
            int victim=(m.flags&EN_PASSANT)?V[PAWN]:V[std::abs(p.board[m.to])];
            return 100000+16*victim-V[std::abs(p.board[m.from])]+V[m.promotion];
        }
        if(killers[ply][0]&&m==*killers[ply][0])return 90000;
        if(killers[ply][1]&&m==*killers[ply][1])return 80000;
        return history_score[p.turn==1?0:1][m.from][m.to];
    }
    void order(const Position& p,std::vector<Move>& moves,const std::optional<Move>& tt,int ply){
        // Compute move priorities once rather than inside every comparison.
        std::vector<std::pair<int,Move>> ranked;
        ranked.reserve(moves.size());
        for(const auto& m:moves)ranked.emplace_back(priority(p,m,tt,ply),m);
        std::stable_sort(ranked.begin(),ranked.end(),[](const auto& a,const auto& b){return a.first>b.first;});
        for(size_t i=0;i<moves.size();++i)moves[i]=ranked[i].second;
    }
    void update_pv(int ply,const Move& m){
        pv[ply].clear();pv[ply].push_back(m);
        pv[ply].insert(pv[ply].end(),pv[ply+1].begin(),pv[ply+1].end());
    }
    int qsearch(const Position& p,int alpha,int beta,int ply,int qdepth){
        if(ply>=MAX_PLY-1)throw AbortSearch{};
        tick(true);pv[ply].clear();
        uint64_t key=zobrist(repetition_key(p));Scope scope(history,key);
        auto moves=legal_moves(p);
        bool checked=in_check(p,p.turn);
        if(moves.empty())return checked?-MATE+ply:0;
        if(draw(p,key))return 0;
        if(!limits.quiescence)return evaluate_position(p);
        int best=-INF;
        if(!checked){
            best=evaluate_position(p);
            if(best>=beta)return best;
            alpha=std::max(alpha,best);
            if(qdepth>=QUIET_Q_LIMIT)return best;
            moves.erase(std::remove_if(moves.begin(),moves.end(),[&](const Move& m){return !tactical(p,m);}),moves.end());
        }else if(qdepth>=CHECK_Q_LIMIT){
            // Do not stand pat in check. Discard the incomplete iteration instead.
            throw AbortSearch{};
        }
        order(p,moves,std::nullopt,ply);
        for(const Move& m:moves){
            int value=-qsearch(make_move(p,m),-beta,-alpha,ply+1,qdepth+1);
            if(value>best){best=value;update_pv(ply,m);}
            alpha=std::max(alpha,value);
            if(alpha>=beta)break;
        }
        return best;
    }
    int negamax(const Position& p,int depth,int alpha,int beta,int ply){
        if(depth<=0)return qsearch(p,alpha,beta,ply,0);
        if(ply>=MAX_PLY-1)throw AbortSearch{};
        tick(false);pv[ply].clear();
        uint64_t key=zobrist(repetition_key(p));Scope scope(history,key);
        auto moves=legal_moves(p);
        if(moves.empty())return in_check(p,p.turn)?-MATE+ply:0;
        if(draw(p,key))return 0;
        const int original_alpha=alpha;
        const uint64_t ctx=context(p);
        std::optional<Move> ttmove;
        Entry* slot=table.empty()?nullptr:&table[key%table.size()];
        if(slot&&slot->depth>=0&&slot->board==key){
            ttmove=slot->move;
            if(slot->context==ctx){
                ++result.tt_hits;
                // Full-window/PV nodes are searched, so published PV is not a guessed TT line.
                if(beta-alpha<=1&&slot->depth>=depth){
                    int v=unpack_mate(slot->score,ply);
                    if(slot->bound==EXACT||(slot->bound==LOWER&&v>=beta)||(slot->bound==UPPER&&v<=alpha))return v;
                }
            }
        }
        order(p,moves,ttmove,ply);
        int best=-INF;Move best_move=moves.front();bool first=true;
        for(const Move& m:moves){
            Position child=make_move(p,m);
            int value;
            if(first)value=-negamax(child,depth-1,-beta,-alpha,ply+1);
            else{
                // Principal variation search, re-search a promising null-window result.
                value=-negamax(child,depth-1,-alpha-1,-alpha,ply+1);
                if(value>alpha&&value<beta)value=-negamax(child,depth-1,-beta,-alpha,ply+1);
            }
            first=false;
            if(value>best){best=value;best_move=m;update_pv(ply,m);}
            alpha=std::max(alpha,value);
            if(alpha>=beta){
                if(!tactical(p,m)){
                    if(!killers[ply][0]||!(m==*killers[ply][0])){
                        killers[ply][1]=killers[ply][0];killers[ply][0]=m;
                    }
                    auto& h=history_score[p.turn==1?0:1][m.from][m.to];
                    h=std::min(70000,h+depth*depth);
                }
                break;
            }
        }
        if(slot&&(slot->board!=key||slot->context!=ctx||slot->depth<=depth)){
            *slot=Entry{key,ctx,best_move,pack_mate(best,ply),depth,
                        best<=original_alpha?UPPER:best>=beta?LOWER:EXACT};
        }
        return best;
    }
    SearchResult run(const Position& root){
        auto legal=legal_moves(root);
        if(legal.empty()){
            result.score_cp=in_check(root,root.turn)?-MATE:0;
            return result;
        }
        uint64_t root_key=zobrist(repetition_key(root));
        {
            Scope scope(history,root_key);
            if(draw(root,root_key))return result;
        }
        // Legal emergency fallback if a tiny budget expires before depth 1.
        result.best=legal.front();result.pv={legal.front()};
        result.score_cp=evaluate_position(root);
        for(int d=1;d<=std::clamp(limits.depth,1,12);++d){
            try{
                int value=negamax(root,d,-INF,INF,0);
                if(pv[0].empty())throw std::logic_error("Search produced no root move");
                result.best=pv[0][0];result.pv=pv[0];result.score_cp=value;result.completed_depth=d;
                if(std::abs(value)>=MATE_BOUND)break;
            }catch(const AbortSearch&){result.stopped=true;break;}
        }
        result.elapsed_ms=elapsed();
        return result;
    }
};
}

int evaluate_deep(const Position& position){return evaluate_position(position);}

SearchResult search_deep(const Position& position,const SearchLimits& limits,
                         const std::vector<std::string>& prior_keys){
    return Searcher(limits,prior_keys).run(position);
}
}
