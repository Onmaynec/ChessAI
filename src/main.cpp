#include "chess.hpp"
#include "search.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <exception>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <unordered_map>
#include <random>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

using namespace chess;
namespace {
using Clock=std::chrono::steady_clock;
std::string join(const std::vector<std::string>& a,size_t start) {
    std::string s;
    for(size_t i=start;i<a.size();++i){if(!s.empty())s+=' ';s+=a[i];}
    return s;
}
int integer(const std::string& s,int min,int max,const std::string& label) {
    size_t used=0;int n=0;
    try{n=std::stoi(s,&used);}catch(...){throw std::invalid_argument("Bad " + label);}
    if(used!=s.size()||n<min||n>max)throw std::invalid_argument("Bad "+label);
    return n;
}
void help(){
    std::cout << "Chess AI Core v0.3.0 (neural self-play training in Python)\n\n"
              << "  chessai inspect [FEN]                 Board and legal moves\n"
              << "  chessai perft DEPTH [FEN]            Verify legal move generator\n"
              << "  chessai divide DEPTH [FEN]           Per-root-move perft counts\n"
              << "  chessai bench                       Reference perft + performance\n"
              << "  chessai selfplay GAMES THREADS FILE [MAX_PLIES] [SEED]\n"
              << "                                      Generate JSONL game records\n"
              << "  chessai teacherdata SAMPLES DEPTH FILE [SEED]\n"
              << "                                      Export supervised positions\n"
              << "  chessai legal-json [FEN]            FEN and legal UCI actions as JSON\n"
              << "  chessai apply MOVE [FEN]            Apply a legal UCI move; print FEN\n"
              << "  chessai play [DEPTH]                Human vs simple baseline\n"
              << "  chessai uci                         Minimal UCI chess engine\n"
              << "  chessai bridge                      Persistent JSONL multi-game training interface\n";
}
void benchmark() {
    struct Case {const char* name;const char* fen;int depth;uint64_t expected;};
    const Case cases[]={
        {"startpos",START_FEN.data(),4,197281},
        {"kiwipete","r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",3,97862},
        {"position3","8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",4,43238},
        {"position5","rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",3,62379},
    };
    uint64_t total=0;double seconds=0;
    for(const auto& c:cases){
        auto p=parse_fen(c.fen);
        auto start=Clock::now();
        uint64_t nodes=perft(p,c.depth);
        double s=std::chrono::duration<double>(Clock::now()-start).count();
        total+=nodes;seconds+=s;
        std::cout<<c.name<<" depth="<<c.depth<<" nodes="<<nodes<<" expected="<<c.expected
                 <<" "<<(nodes==c.expected?"PASS":"FAIL")<<" time="<<std::fixed<<std::setprecision(3)<<s<<"s\n";
        if(nodes!=c.expected)throw std::runtime_error("Perft benchmark FAILED");
    }
    std::cout<<"Total nodes: "<<total<<" | total time: "<<std::fixed<<std::setprecision(3)<<seconds
             <<" s | measured nodes/sec: "<<uint64_t(total/std::max(seconds,1e-9))<<"\n";
}
struct Game {
    int id=0;unsigned long long seed=0;
    std::vector<std::string> moves;
    std::string end_fen,result="*",reason="max_plies";
};
Game selfplay(int id,uint64_t base_seed,int max_plies) {
    Game game;game.id=id;
    game.seed=base_seed+uint64_t(id)*0x9e3779b97f4a7c15ULL;
    std::mt19937_64 rng(game.seed);
    Position p=parse_fen(std::string(START_FEN));
    std::vector<std::string> keys;
    keys.push_back(repetition_key(p));
    for(int ply=0;ply<=max_plies;++ply) {
        Outcome end=outcome(p,keys);
        if(end.finished){game.result=end.result;game.reason=end.reason;break;}
        if(ply==max_plies)break;
        auto moves=legal_moves(p);
        std::uniform_int_distribution<size_t> choose(0,moves.size()-1);
        const Move m=moves[choose(rng)];
        game.moves.push_back(uci(m));
        p=make_move(p,m);
        keys.push_back(repetition_key(p));
    }
    game.end_fen=to_fen(p);
    return game;
}
std::string game_json(const Game& g) {
    std::ostringstream o;
    o<<"{\"game_id\":"<<g.id<<",\"seed\":"<<g.seed
      <<",\"start_fen\":\""<<START_FEN<<"\",\"policy\":\"random\""
      <<",\"result\":\""<<g.result<<"\",\"reason\":\""<<g.reason
      <<"\",\"plies\":"<<g.moves.size()<<",\"moves\":[";
    for(size_t i=0;i<g.moves.size();++i){if(i)o<<',';o<<'"'<<g.moves[i]<<'"';}
    o<<"],\"final_fen\":\""<<g.end_fen<<"\"}";
    return o.str();
}
void generate(int games,int threads,const std::string& path,int max_plies,uint64_t seed) {
    std::ofstream file(path,std::ios::out|std::ios::trunc);
    if(!file)throw std::runtime_error("Cannot open output file: "+path);
    auto start=Clock::now();
    std::mutex output_mutex;
    std::atomic<int> next{0},done{0};
    std::atomic<uint64_t> plies{0};
    std::vector<std::thread> workers;
    for(int t=0;t<std::min(games,threads);++t)workers.emplace_back([&]{
        while(true){int id=next.fetch_add(1);if(id>=games)break;
            auto game=selfplay(id,seed,max_plies);
            plies+=game.moves.size();
            auto line=game_json(game);
            {std::lock_guard<std::mutex> lock(output_mutex);file<<line<<'\n';}
            ++done;
        }
    });
    for(auto& w:workers)w.join();
    file.flush();
    if(!file)throw std::runtime_error("Write error: "+path);
    double seconds=std::chrono::duration<double>(Clock::now()-start).count();
    std::cout<<"Games: "<<done<<" | plies: "<<plies<<" | seconds: "<<std::fixed<<std::setprecision(3)
             <<seconds<<" | games/sec: "<<std::setprecision(2)<<games/std::max(seconds,1e-9)
             <<" | plies/sec: "<<plies/std::max(seconds,1e-9)<<"\nSaved: "<<path<<"\n";
    std::cout<<"NOTE: random policy, not a trained neural network; games reaching max_plies are UNFINISHED.\n";
}
void export_teacher(int count,int depth,const std::string& path,uint64_t seed) {
    std::ofstream file(path,std::ios::trunc);
    if(!file)throw std::runtime_error("Cannot open teacher dataset: "+path);
    std::mt19937_64 rng(seed);
    const auto base=parse_fen(std::string(START_FEN));
    int written=0,attempts=0;
    auto started=Clock::now();
    while(written<count && attempts<count*30){
        ++attempts;
        Position p=base;
        const int opening_plies=4+int(rng()%37);
        for(int j=0;j<opening_plies;++j){
            auto moves=legal_moves(p);
            if(moves.empty()||insufficient_material(p)||p.halfmove>=100)break;
            // Sample plausible positions as well as deliberately diverse ones.
            // A shallow baseline move is not a strong grandmaster teacher.
            if(j>3 && (rng()%4)!=0){
                const auto candidate=search_baseline(p,1);
                if(!candidate.best)break;
                p=make_move(p,*candidate.best);
            }else{
                p=make_move(p,moves[size_t(rng()%moves.size())]);
            }
        }
        if(legal_moves(p).empty() || insufficient_material(p) || p.halfmove>=100)continue;
        const auto prediction=search_baseline(p,depth);
        if(!prediction.best)continue;
        file<<"{\"fen\":\""<<to_fen(p)<<"\",\"best_move\":\""<<uci(*prediction.best)
            <<"\",\"score_cp\":"<<prediction.score_cp
            <<",\"teacher\":\"chessai_baseline_d"<<depth<<"\",\"sample_id\":"<<written
            <<",\"legal_moves\":[";
        auto legal=legal_moves(p);
        for(size_t k=0;k<legal.size();++k){if(k)file<<',';file<<'"'<<uci(legal[k])<<'"';}
        file<<"]}\n";
        ++written;
    }
    file.flush();
    if(!file)throw std::runtime_error("Teacher dataset write failure");
    if(written!=count)throw std::runtime_error("Could not generate enough valid positions");
    auto seconds=std::chrono::duration<double>(Clock::now()-started).count();
    std::cout<<"Teacher rows: "<<written<<" | depth: "<<depth<<" | seconds: "
             <<std::fixed<<std::setprecision(2)<<seconds<<" | saved: "<<path<<"\n"
             <<"WARNING: targets come from the WEAK built-in baseline, not Stockfish.\n";
}

// Persistent multi-game interface for batched neural self-play. A single C++
// process owns all boards; Python never needs to emulate chess rules.
struct BridgeGame {
    Position p=parse_fen(std::string(START_FEN));
    std::vector<std::string> keys{repetition_key(p)};
    int plies=0;
};
void emit_bridge(int id, const BridgeGame& g) {
    const Outcome end=outcome(g.p,g.keys);
    std::cout<<"{\"game_id\":"<<id<<",\"fen\":\""<<to_fen(g.p)
             <<"\",\"result\":\""<<end.result<<"\",\"reason\":\""<<end.reason
             <<"\",\"finished\":"<<(end.finished?"true":"false")
             <<",\"plies\":"<<g.plies<<",\"legal_moves\":[";
    if(!end.finished){
        auto legal=legal_moves(g.p);
        for(size_t i=0;i<legal.size();++i){if(i)std::cout<<',';std::cout<<'"'<<uci(legal[i])<<'"';}
    }
    std::cout<<"]}"<<std::endl;
}
void bridge() {
    std::unordered_map<int,BridgeGame> games;
    std::string command;
    while(std::getline(std::cin,command)) {
        try {
            std::istringstream in(command);
            std::string operation;int id=-1;
            if(!(in>>operation))continue;
            if(operation=="quit")break;
            if(!(in>>id) || id<0 || id>1000000)throw std::invalid_argument("invalid game_id");
            if(operation=="new") {
                std::string rest;std::getline(in,rest);
                BridgeGame g;
                if(rest.find_first_not_of(" \t")!=std::string::npos){
                    g.p=parse_fen(rest.substr(rest.find_first_not_of(" \t")));
                    g.keys={repetition_key(g.p)};
                }
                games[id]=std::move(g);
                emit_bridge(id,games.at(id));
            } else if(operation=="step") {
                auto it=games.find(id);
                if(it==games.end())throw std::invalid_argument("unknown game_id");
                if(outcome(it->second.p,it->second.keys).finished)throw std::invalid_argument("game already over");
                std::string move,extra;
                if(!(in>>move) || (in>>extra))throw std::invalid_argument("expected one UCI move");
                if(!apply_uci(it->second.p,move))throw std::invalid_argument("illegal move");
                it->second.keys.push_back(repetition_key(it->second.p));
                ++it->second.plies;
                emit_bridge(id,it->second);
            } else if(operation=="state") {
                auto it=games.find(id);
                if(it==games.end())throw std::invalid_argument("unknown game_id");
                emit_bridge(id,it->second);
            } else if(operation=="drop") {
                games.erase(id);
                std::cout<<"{\"game_id\":"<<id<<",\"dropped\":true}"<<std::endl;
            } else throw std::invalid_argument("unknown bridge command");
        } catch(const std::exception& e) {
            // Errors are deliberately generic; no unescaped arbitrary strings in JSON.
            std::cerr<<"Bridge command error: "<<e.what()<<'\n';
            std::cout<<"{\"error\":\"invalid bridge command\"}"<<std::endl;
        }
    }
}

void interactive(int depth){
    Position p=parse_fen(std::string(START_FEN));std::string input;
    std::vector<std::string> keys{repetition_key(p)};
    std::cout<<"You are White. Enter UCI moves like e2e4, e7e8q, or 'quit'.\n";
    while(true){
        std::cout<<'\n'<<board_ascii(p);
        auto end=outcome(p,keys);
        if(end.finished){std::cout<<"Game over: "<<end.result<<" ("<<end.reason<<")\n";break;}
        if(p.turn==1){
            std::cout<<"Your move > "<<std::flush;
            if(!std::getline(std::cin,input)||input=="quit")break;
            if(input=="fen"){std::cout<<to_fen(p)<<'\n';continue;}
            if(input=="moves"){
                for(auto m:legal_moves(p))std::cout<<uci(m)<<' ';
                std::cout<<'\n';continue;
            }
            if(!apply_uci(p,input)){std::cout<<"Illegal move; use UCI coordinate notation.\n";continue;}
        }else{
            auto result=search_baseline(p,depth);
            if(!result.best)break;
            std::cout<<"Baseline engine plays "<<uci(*result.best)<<" (score cp "<<result.score_cp<<")\n";
            p=make_move(p,*result.best);
        }
        keys.push_back(repetition_key(p));
    }
}
void uci_session(){
    Position p=parse_fen(std::string(START_FEN));std::string line;
    while(std::getline(std::cin,line)){
        std::istringstream in(line);std::string cmd;
        in>>cmd;
        if(cmd=="quit")break;
        if(cmd=="uci")std::cout<<"id name ChessAI-Core-0.4-Baseline\nid author Local Chess AI Project\nuciok\n";
        else if(cmd=="isready")std::cout<<"readyok\n";
        else if(cmd=="ucinewgame")p=parse_fen(std::string(START_FEN));
        else if(cmd=="position"){
            std::string first;in>>first;
            if(first=="startpos")p=parse_fen(std::string(START_FEN));
            else if(first=="fen"){
                std::string parts[6],fen;
                bool ok=true;
                for(auto& part:parts)if(!(in>>part))ok=false;
                if(!ok){std::cout<<"info string Invalid position FEN\n";continue;}
                for(auto& part:parts){if(!fen.empty())fen+=' ';fen+=part;}
                try{p=parse_fen(fen);}catch(const std::exception& ex){std::cout<<"info string "<<ex.what()<<'\n';continue;}
            }else continue;
            std::string marker;in>>marker;
            if(marker=="moves"){
                std::string m;
                while(in>>m)if(!apply_uci(p,m)){
                    std::cout<<"info string Illegal move in position: "<<m<<'\n';break;
                }
            }
        } else if(cmd=="go") {
            int depth=3;std::string token;
            while(in>>token)if(token=="depth"){
                std::string count;
                if(in>>count)try{depth=integer(count,1,6,"depth");}catch(...){}
            }
            auto result=search_baseline(p,depth);
            std::cout<<"info depth "<<depth<<" score cp "<<result.score_cp<<" nodes "<<result.nodes<<'\n';
            std::cout<<"bestmove "<<(result.best?uci(*result.best):"0000")<<'\n';
        }
        std::cout.flush();
    }
}
}

int main(int argc,char** argv){
    try{
        std::vector<std::string> a(argv+1,argv+argc);
        if(a.empty()||a[0]=="--help"||a[0]=="help"){help();return 0;}
        if(a[0]=="bench"){benchmark();return 0;}
        if(a[0]=="uci"){uci_session();return 0;}
        if(a[0]=="bridge"){bridge();return 0;}
        if(a[0]=="teacherdata") {
            if(a.size()<4)throw std::invalid_argument("Usage: teacherdata SAMPLES DEPTH FILE [SEED]");
            const int n=integer(a[1],1,5000000,"samples");
            const int depth=integer(a[2],1,4,"depth");
            const uint64_t seed=a.size()>4?std::stoull(a[4]):42ULL;
            export_teacher(n,depth,a[3],seed);return 0;
        }
        if(a[0]=="apply"){
            if(a.size()<2)throw std::invalid_argument("Usage: apply MOVE [FEN]");
            Position p=parse_fen(a.size()>2?join(a,2):std::string(START_FEN));
            if(!apply_uci(p,a[1]))throw std::invalid_argument("Illegal move: "+a[1]);
            std::cout<<to_fen(p)<<'\n';return 0;
        }
        if(a[0]=="legal-json"){
            Position p=parse_fen(a.size()>1?join(a,1):std::string(START_FEN));
            std::cout<<"{\"fen\":\""<<to_fen(p)<<"\",\"moves\":[";
            auto moves=legal_moves(p);
            for(size_t i=0;i<moves.size();++i){if(i)std::cout<<',';std::cout<<'"'<<uci(moves[i])<<'"';}
            std::cout<<"]}\n";return 0;
        }
        if(a[0]=="inspect"){
            Position p=parse_fen(a.size()>1?join(a,1):std::string(START_FEN));
            std::cout<<board_ascii(p)<<"FEN: "<<to_fen(p)<<"\nLegal moves: ";
            for(const auto& m:legal_moves(p))std::cout<<uci(m)<<' ';
            std::cout<<'\n';return 0;
        }
        if(a[0]=="perft" || a[0]=="divide"){
            if(a.size()<2)throw std::invalid_argument("Missing depth");
            int depth=integer(a[1],0,8,"depth");
            Position p=parse_fen(a.size()>2?join(a,2):std::string(START_FEN));
            auto start=Clock::now();uint64_t sum=0;
            if(a[0]=="divide" && depth>0){
                auto moves=legal_moves(p);
                std::sort(moves.begin(),moves.end(),[](const Move& x,const Move& y){return uci(x)<uci(y);});
                for(const Move& m:moves){uint64_t n=perft(make_move(p,m),depth-1);
                    std::cout<<uci(m)<<": "<<n<<'\n';sum+=n;}
            }else sum=perft(p,depth);
            double sec=std::chrono::duration<double>(Clock::now()-start).count();
            std::cout<<"Nodes: "<<sum<<" | seconds: "<<std::fixed<<std::setprecision(3)<<sec
                <<" | nodes/sec: "<<uint64_t(sum/std::max(sec,1e-9))<<'\n';
            return 0;
        }
        if(a[0]=="selfplay"){
            if(a.size()<4)throw std::invalid_argument("Usage: selfplay GAMES THREADS FILE [MAX_PLIES] [SEED]");
            int games=integer(a[1],1,10000000,"games"),threads=integer(a[2],1,256,"threads");
            int max_plies=a.size()>4?integer(a[4],1,10000,"max_plies"):300;
            uint64_t seed=a.size()>5?std::stoull(a[5]):20261123ULL;
            generate(games,threads,a[3],max_plies,seed);return 0;
        }
        if(a[0]=="play"){
            interactive(a.size()>1?integer(a[1],1,6,"depth"):3);return 0;
        }
        help();return 1;
    }catch(const std::exception& ex){std::cerr<<"Error: "<<ex.what()<<'\n';return 2;}
}
