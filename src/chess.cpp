#include "chess.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <cstdlib>
#include <sstream>
#include <stdexcept>

namespace chess {
namespace {
inline bool inside(int f, int r) { return f>=0 && f<8 && r>=0 && r<8; }
inline int file(int s) { return s%8; }
inline int rank(int s) { return s/8; }
inline int color(int p) { return (p>0) - (p<0); }
inline int type(int p) { return std::abs(p); }
char piece_char(int p) {
    static constexpr char names[] = ".PNBRQK";
    char c=names[type(p)];
    return p<0?char(std::tolower(static_cast<unsigned char>(c))):c;
}
int parse_piece(char c) {
    const std::string up="PNBRQK";
    char u=char(std::toupper(static_cast<unsigned char>(c)));
    auto i=up.find(u);
    if(i==std::string::npos) throw std::invalid_argument("Invalid FEN piece");
    return (std::islower(static_cast<unsigned char>(c))?-1:1)*int(i+1);
}
void promote_or_push(std::vector<Move>& v, int from, int to, int flags, bool promo) {
    if(promo) for(int p : {QUEEN,ROOK,BISHOP,KNIGHT}) v.push_back({from,to,int8_t(p),uint8_t(flags)});
    else v.push_back({from,to,EMPTY,uint8_t(flags)});
}
std::vector<Move> pseudo_moves(const Position& p) {
    std::vector<Move> v;
    v.reserve(64);
    constexpr std::array<std::array<int,2>,8> knight{{{1,2},{2,1},{2,-1},{1,-2},{-1,-2},{-2,-1},{-2,1},{-1,2}}};
    constexpr std::array<std::array<int,2>,8> directions{{{0,1},{1,0},{0,-1},{-1,0},{1,1},{1,-1},{-1,-1},{-1,1}}};
    for(int from=0;from<64;++from) {
        const int pc=p.board[from], side=color(pc), kind=type(pc);
        if(side!=p.turn) continue;
        const int f=file(from),r=rank(from);
        if(kind==PAWN) {
            int ahead=from+side*8;
            bool promo=(r+side==0 || r+side==7);
            if(ahead>=0 && ahead<64 && p.board[ahead]==EMPTY) {
                promote_or_push(v,from,ahead,NORMAL,promo);
                int two=from+side*16;
                if(r==(side==1?1:6) && p.board[two]==EMPTY)
                    v.push_back({from,two,EMPTY,DOUBLE_PAWN});
            }
            for(int df : {-1,1}) {
                int ff=f+df, rr=r+side;
                if(!inside(ff,rr)) continue;
                int target=rr*8+ff;
                if(color(p.board[target])==-side && type(p.board[target])!=KING)
                    promote_or_push(v,from,target,NORMAL,promo);
                else if(target==p.en_passant && p.board[target]==EMPTY &&
                        p.board[target-side*8]==-side*PAWN)
                    v.push_back({from,target,EMPTY,EN_PASSANT});
            }
        } else if(kind==KNIGHT) {
            for(auto d:knight) {
                int ff=f+d[0],rr=r+d[1];
                if(!inside(ff,rr))continue;
                int target=rr*8+ff;
                if(color(p.board[target])!=side && type(p.board[target])!=KING)
                    v.push_back({from,target,EMPTY,NORMAL});
            }
        } else {
            for(int d=0;d<8;++d) {
                if(kind==BISHOP && d<4)continue;
                if(kind==ROOK && d>=4)continue;
                int ff=f+directions[d][0],rr=r+directions[d][1];
                while(inside(ff,rr)) {
                    int target=rr*8+ff;
                    if(color(p.board[target])==side || type(p.board[target])==KING)break;
                    v.push_back({from,target,EMPTY,NORMAL});
                    if(p.board[target]!=EMPTY || kind==KING)break;
                    ff+=directions[d][0];rr+=directions[d][1];
                }
            }
            if(kind==KING) {
                if(side==1 && from==4 && p.board[4]==KING && !in_check(p,side)) {
                    if((p.castle&1) && p.board[7]==ROOK && p.board[5]==EMPTY && p.board[6]==EMPTY &&
                       !is_square_attacked(p,5,-1) && !is_square_attacked(p,6,-1))
                        v.push_back({4,6,EMPTY,CASTLE});
                    if((p.castle&2) && p.board[0]==ROOK && p.board[1]==EMPTY && p.board[2]==EMPTY && p.board[3]==EMPTY &&
                       !is_square_attacked(p,3,-1) && !is_square_attacked(p,2,-1))
                        v.push_back({4,2,EMPTY,CASTLE});
                }
                if(side==-1 && from==60 && p.board[60]==-KING && !in_check(p,side)) {
                    if((p.castle&4) && p.board[63]==-ROOK && p.board[61]==EMPTY && p.board[62]==EMPTY &&
                       !is_square_attacked(p,61,1) && !is_square_attacked(p,62,1))
                        v.push_back({60,62,EMPTY,CASTLE});
                    if((p.castle&8) && p.board[56]==-ROOK && p.board[57]==EMPTY && p.board[58]==EMPTY && p.board[59]==EMPTY &&
                       !is_square_attacked(p,59,1) && !is_square_attacked(p,58,1))
                        v.push_back({60,58,EMPTY,CASTLE});
                }
            }
        }
    }
    return v;
}
}

Position parse_fen(const std::string& fen) {
    Position p;
    std::istringstream in(fen);
    std::string board, turn, castle, ep;
    int half=0,full=1;
    if(!(in>>board>>turn>>castle>>ep>>half>>full))
        throw std::invalid_argument("FEN must include six fields");
    std::string extra;
    if(in>>extra)throw std::invalid_argument("Too many FEN fields");
    int rr=7,ff=0,king_w=0,king_b=0;
    for(char c:board) {
        if(c=='/') {if(ff!=8 || rr<=0)throw std::invalid_argument("Invalid FEN rank");--rr;ff=0;continue;}
        if(c>='1'&&c<='8') {ff+=c-'0';if(ff>8)throw std::invalid_argument("Invalid FEN rank width");continue;}
        if(!inside(ff,rr)) throw std::invalid_argument("Invalid FEN square");
        int pc=parse_piece(c);
        if(pc==KING)++king_w;
        if(pc==-KING)++king_b;
        if(type(pc)==PAWN && (rr==0 || rr==7))throw std::invalid_argument("Pawn on promotion rank");
        p.board[rr*8+ff]=int8_t(pc);++ff;
    }
    if(rr!=0||ff!=8||king_w!=1||king_b!=1)throw std::invalid_argument("Invalid FEN board/kings");
    if(turn=="w")p.turn=1;
    else if(turn=="b")p.turn=-1;
    else throw std::invalid_argument("Invalid turn in FEN");
    if(castle!="-") {
        for(char c:castle) {
            uint8_t bit=0;
            switch(c){case 'K':bit=1;break;case 'Q':bit=2;break;case 'k':bit=4;break;case 'q':bit=8;break;default:throw std::invalid_argument("Invalid castling rights");}
            if(p.castle & bit)throw std::invalid_argument("Duplicate castling right");
            p.castle|=bit;
        }
    }
    if(ep!="-") {
        int s=text_to_square(ep);
        if(s<0 || rank(s)!=(p.turn==1?5:2) || p.board[s]!=EMPTY)
            throw std::invalid_argument("Invalid en passant target");
        // The pawn which made the preceding two-square move must still be present.
        const int captured_pawn_square=s-p.turn*8;
        const int pawn_start_square=s+p.turn*8;
        if(p.board[captured_pawn_square]!=-p.turn*PAWN || p.board[pawn_start_square]!=EMPTY)
            throw std::invalid_argument("Invalid en passant pawn history");
        p.en_passant=int8_t(s);
    }
    if(half<0 || half>65535 || full<1 || full>65535)throw std::invalid_argument("Invalid move counters");
    p.halfmove=uint16_t(half);p.fullmove=uint16_t(full);
    // The side that just moved cannot have left its own king in check.
    if(in_check(p,-p.turn))throw std::invalid_argument("Illegal FEN: previous mover's king is in check");
    return p;
}

std::string to_fen(const Position& p) {
    std::ostringstream o;
    for(int r=7;r>=0;--r){
        int blanks=0;
        for(int f=0;f<8;++f){int pc=p.board[r*8+f];if(pc==0){++blanks;continue;}
            if(blanks){o<<blanks;blanks=0;}o<<piece_char(pc);
        }
        if(blanks)o<<blanks;
        if(r)o<<'/';
    }
    o<<(p.turn==1?" w ":" b ");
    if(p.castle==0)o<<'-';
    else {if(p.castle&1)o<<'K';if(p.castle&2)o<<'Q';if(p.castle&4)o<<'k';if(p.castle&8)o<<'q';}
    o<<' '<<(p.en_passant<0?"-":square_to_text(p.en_passant));
    o<<' '<<p.halfmove<<' '<<p.fullmove;
    return o.str();
}

std::string square_to_text(int s) {
    if(s<0||s>=64)return "??";
    return std::string{char('a'+file(s)),char('1'+rank(s))};
}
int text_to_square(std::string_view t) {
    if(t.size()!=2 || t[0]<'a'||t[0]>'h'||t[1]<'1'||t[1]>'8')return -1;
    return (t[1]-'1')*8+(t[0]-'a');
}
std::string uci(const Move& m) {
    std::string result=square_to_text(m.from)+square_to_text(m.to);
    if(m.promotion)result+=char(std::tolower(static_cast<unsigned char>(piece_char(m.promotion))));
    return result;
}

bool is_square_attacked(const Position& p,int sq,int by) {
    if(sq<0 || sq>=64)return false;
    const int f=file(sq),r=rank(sq);
    int pr=r-by;
    if(pr>=0 && pr<8){
        for(int pf:{f-1,f+1})if(pf>=0 && pf<8 && p.board[pr*8+pf]==by*PAWN)return true;
    }
    constexpr std::array<std::array<int,2>,8> knight{{{1,2},{2,1},{2,-1},{1,-2},{-1,-2},{-2,-1},{-2,1},{-1,2}}};
    for(auto d:knight){int ff=f+d[0],rr=r+d[1];if(inside(ff,rr)&&p.board[rr*8+ff]==by*KNIGHT)return true;}
    constexpr std::array<std::array<int,2>,8> dirs{{{0,1},{1,0},{0,-1},{-1,0},{1,1},{1,-1},{-1,-1},{-1,1}}};
    for(int d=0;d<8;++d) {
        int ff=f+dirs[d][0],rr=r+dirs[d][1],distance=1;
        while(inside(ff,rr)){
            int pc=p.board[rr*8+ff];
            if(pc!=EMPTY){
                if(color(pc)==by && ((distance==1 && type(pc)==KING) || type(pc)==QUEEN ||
                    (d<4 && type(pc)==ROOK) || (d>=4 && type(pc)==BISHOP)))return true;
                break;
            }
            ++distance;ff+=dirs[d][0];rr+=dirs[d][1];
        }
    }
    return false;
}
bool in_check(const Position& p,int side) {
    for(int s=0;s<64;++s) if(p.board[s]==side*KING)
        return is_square_attacked(p,s,-side);
    return true;
}

Position make_move(const Position& p,const Move& m) {
    Position n=p;
    int piece=p.board[m.from],target=p.board[m.to],side=p.turn;
    n.board[m.from]=EMPTY;
    n.board[m.to]=m.promotion?int8_t(side*m.promotion):int8_t(piece);
    if(m.flags&EN_PASSANT)n.board[m.to-side*8]=EMPTY;
    if(m.flags&CASTLE){
        int rf=m.to>m.from?m.from+3:m.from-4;
        int rt=m.to>m.from?m.from+1:m.from-1;
        n.board[rt]=n.board[rf];n.board[rf]=EMPTY;
    }
    if(type(piece)==KING)n.castle&=uint8_t(side==1?~3:~12);
    // Clear castling rights when a corner rook moves or is captured.
    for(auto info:std::array<std::array<int,2>,4>{{{0,2},{7,1},{56,8},{63,4}}}) {
        if(m.from==info[0] || m.to==info[0])n.castle&=uint8_t(~info[1]);
    }
    n.en_passant=(type(piece)==PAWN && std::abs(m.to-m.from)==16)?int8_t((m.from+m.to)/2):-1;
    n.halfmove=uint16_t((type(piece)==PAWN||target!=EMPTY||m.flags&EN_PASSANT)?0:p.halfmove+1);
    n.fullmove=uint16_t(p.fullmove+(side==-1));
    n.turn=int8_t(-side);
    return n;
}

std::vector<Move> legal_moves(const Position& p) {
    auto possible=pseudo_moves(p);
    std::vector<Move> result;
    result.reserve(possible.size());
    for(const Move& m:possible) if(!in_check(make_move(p,m),p.turn))result.push_back(m);
    return result;
}

bool apply_uci(Position& p,const std::string& txt) {
    if(txt.size()!=4 && txt.size()!=5)return false;
    for(const Move& m:legal_moves(p))if(uci(m)==txt){p=make_move(p,m);return true;}
    return false;
}

uint64_t perft(const Position& p,int depth) {
    if(depth<0)throw std::invalid_argument("Negative perft depth");
    if(depth==0)return 1;
    auto moves=legal_moves(p);
    if(depth==1)return moves.size();
    uint64_t total=0;
    for(const Move& m:moves)total+=perft(make_move(p,m),depth-1);
    return total;
}

std::string repetition_key(const Position& p) {
    // Legal-en-passant rights affect position identity; an uncapturable target does not.
    int ep=-1;
    if(p.en_passant>=0){
        int to=p.en_passant,from_rank=rank(to)-p.turn;
        for(int f:{file(to)-1,file(to)+1}){
            if(!inside(f,from_rank))continue;
            int from=from_rank*8+f;
            if(p.board[from]!=p.turn*PAWN)continue;
            if(!in_check(make_move(p,{from,to,EMPTY,EN_PASSANT}),p.turn)){ep=to;break;}
        }
    }
    std::string k;
    k.reserve(68);
    for(int x:p.board)k+=char(x+int('N')); // fixed-width collision-free byte alphabet for -6..6
    k+=char(p.turn+int('N'));
    k+=char(p.castle+int('N'));
    k+=char(ep+1+int('N'));
    return k;
}

bool insufficient_material(const Position& p) {
    int count=0, bishop_color=-1;
    for(int s=0;s<64;++s){int pc=p.board[s],kind=type(pc);
        if(kind==EMPTY||kind==KING)continue;
        if(kind==PAWN||kind==ROOK||kind==QUEEN)return false;
        ++count;
        if(kind==KNIGHT){if(count>1)return false;bishop_color=-2;}
        else if(kind==BISHOP) {
            int bc=(file(s)+rank(s))%2;
            if(bishop_color==-1)bishop_color=bc;
            else if(bishop_color!=bc)return false;
        }
    }
    return count==0 || count==1 || (bishop_color>=0);
}

Outcome outcome(const Position& p,const std::vector<std::string>& keys) {
    const auto moves=legal_moves(p);
    if(moves.empty()){
        if(in_check(p,p.turn))return {p.turn==1?"0-1":"1-0","checkmate",true};
        return {"1/2-1/2","stalemate",true};
    }
    if(insufficient_material(p))return {"1/2-1/2","insufficient_material",true};
    if(p.halfmove>=150)return {"1/2-1/2","75_move_rule",true};
    const std::string key=repetition_key(p);
    const int repeats=int(std::count(keys.begin(),keys.end(),key));
    if(repeats>=5)return {"1/2-1/2","fivefold_repetition",true};
    // Explicit self-play policy: automatically claim draws whenever eligible.
    if(p.halfmove>=100)return {"1/2-1/2","50_move_rule_claimed",true};
    if(repeats>=3)return {"1/2-1/2","threefold_repetition_claimed",true};
    return {};
}

std::string board_ascii(const Position& p) {
    std::ostringstream o;
    for(int r=7;r>=0;--r){
        o<<(r+1)<<"  ";
        for(int f=0;f<8;++f){int pc=p.board[r*8+f];o<<piece_char(pc)<<' ';}
        o<<'\n';
    }
    o<<"\n   a b c d e f g h\n";
    o<<(p.turn==1?"White":"Black")<<" to move\n";
    return o.str();
}
}
