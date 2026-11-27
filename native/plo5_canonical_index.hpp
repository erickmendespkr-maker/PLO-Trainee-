#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace plo5 {
// Rank-major matrix: rank 0=2 ... 12=A; suit 0=c,1=d,2=h,3=s.
// Each cell: 0 absent, 1 hero, 2 flop, 3 turn, 4 river.
// V1 ordering: lexicographic rank rows, suit columns sorted by signature.
using Matrix = std::array<std::array<uint8_t,4>,13>;
using Counts = std::array<int,4>;
class CanonicalIndex {
    struct Row { std::array<uint8_t,4> v; Counts n{}; int splits=0, desc=0; };
    struct Edge { uint64_t end; uint16_t row; uint8_t mask, count; };
    struct State { uint64_t total=0; bool ready=false; std::vector<Edge> edges; };
    std::array<Row,625> rows_{};
    std::array<State,14*8*96> states_{};
    Counts cap_;
    static int pack(Counts c) { return ((c[0]*4+c[1])*2+c[2])*2+c[3]; }
    static Counts unpack(int k) { return {k/16,(k/4)%4,(k/2)%2,k%2}; }
    static int sum(Counts c) { return c[0]+c[1]+c[2]+c[3]; }
    State& state(int r,int m,int c) { return states_[(r*8+m)*96+c]; }
    const State& state(int r,int m,int c) const { return states_[(r*8+m)*96+c]; }
    uint64_t build(int r,int mask,int k) {
        auto& s=state(r,mask,k);
        if(s.ready) return s.total;
        s.ready=true;
        if(k==0) { s.total=1; return 1; }
        auto c=unpack(k);
        if(r==13 || sum(c)>4*(13-r)) return 0;
        for(int i=0;i<625;++i) {
            const auto& row=rows_[i];
            if(row.desc & mask) continue;
            Counts next=c;
            bool ok=true;
            for(int j=0;j<4;++j) { next[j]-=row.n[j]; if(next[j]<0) ok=false; }
            if(!ok) continue;
            int nm=mask & ~row.splits, nk=pack(next);
            auto n=build(r+1,nm,nk);
            if(n) { s.total+=n; s.edges.push_back({s.total,uint16_t(i),uint8_t(nm),uint8_t(nk)}); }
        }
        return s.total;
    }
    static int code(const std::array<uint8_t,4>& v) { int x=0; for(auto a:v) x=x*5+a; return x; }
public:
    explicit CanonicalIndex(int board_cards) {
        if(board_cards!=0 && (board_cards<3 || board_cards>5)) throw std::invalid_argument("board must have 0,3,4,5 cards");
        cap_={5,board_cards?3:0,board_cards>=4,board_cards==5};
        for(int i=0;i<625;++i) {
            auto& row=rows_[i]; int x=i;
            for(int j=3;j>=0;--j) { row.v[j]=x%5; x/=5; if(row.v[j]) ++row.n[row.v[j]-1]; }
            for(int j=0;j<3;++j) { if(row.v[j]!=row.v[j+1]) row.splits|=1<<j; if(row.v[j]>row.v[j+1]) row.desc|=1<<j; }
        }
        build(0,7,pack(cap_));
    }
    uint64_t size() const { return state(0,7,pack(cap_)).total; }
    size_t edge_count() const { size_t n=0; for(auto& s:states_) n+=s.edges.size(); return n; }
    static Matrix canonical(Matrix a) {
        std::array<int,4> order={0,1,2,3};
        std::sort(order.begin(),order.end(),[&](int x,int y){ for(auto& row:a) if(row[x]!=row[y]) return row[x]<row[y]; return false; });
        Matrix b{}; for(int r=0;r<13;++r) for(int j=0;j<4;++j) b[r][j]=a[r][order[j]]; return b;
    }
    uint64_t rank(Matrix a) const {
        Counts c{}; for(auto& row:a) for(auto v:row) { if(v>4) throw std::invalid_argument("invalid cell"); if(v) ++c[v-1]; }
        if(c!=cap_) throw std::invalid_argument("wrong card counts");
        a=canonical(a); uint64_t id=0; int m=7,k=pack(cap_);
        for(int r=0;r<13 && k;++r) {
            auto& e=state(r,m,k).edges; int v=code(a[r]);
            auto it=std::lower_bound(e.begin(),e.end(),v,[](const Edge& x,int y){return x.row<y;});
            if(it==e.end() || it->row!=v) throw std::logic_error("invalid canonical path");
            if(it!=e.begin()) id+=(it-1)->end;
            m=it->mask; k=it->count;
        }
        return id;
    }
    Matrix unrank(uint64_t id) const {
        if(id>=size()) throw std::out_of_range("index outside street");
        Matrix a{}; int m=7,k=pack(cap_);
        for(int r=0;r<13 && k;++r) {
            auto& e=state(r,m,k).edges;
            auto it=std::upper_bound(e.begin(),e.end(),id,[](uint64_t x,const Edge& y){return x<y.end;});
            if(it==e.end()) throw std::logic_error("invalid index path");
            if(it!=e.begin()) id-=(it-1)->end;
            a[r]=rows_[it->row].v; m=it->mask; k=it->count;
        }
        return a;
    }
    static Matrix from_cards(const std::vector<int>& hero,const std::vector<int>& board) {
        if(hero.size()!=5 || (board.size()!=0 && (board.size()<3 || board.size()>5))) throw std::invalid_argument("wrong card counts");
        Matrix a{};
        auto put=[&](int x,uint8_t v){ if(x<0 || x>=52) throw std::invalid_argument("invalid card"); auto& p=a[x/4][x%4]; if(p) throw std::invalid_argument("duplicate card"); p=v; };
        for(int x:hero) put(x,1);
        for(size_t i=0;i<board.size();++i) put(board[i],i<3?2:uint8_t(i));
        return a;
    }
};
} // namespace plo5
