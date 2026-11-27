#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace plo5 {
// Exact current-board strength; only river is final showdown equity.
struct RelativeStrength {
    uint16_t hero=0, board_nuts=0, opponent_max=0;
    uint64_t wins=0,ties=0,losses=0;
    bool absolute_nuts() const { return hero==board_nuts; }
    bool cannot_lose_now() const { return losses==0; }
    double share_now() const { return (wins+0.5*ties)/(wins+ties+losses); }
};
using CardMask=uint64_t;
inline int pop(CardMask x){return __builtin_popcountll(x);}
inline int low(CardMask x){return __builtin_ctzll(x);}
inline uint64_t combinations(int n,int k){
    if(n<k)return 0;
    uint64_t v=1;for(int i=1;i<=k;++i)v=v*(n-i+1)/i;return v;
}
inline uint64_t cliques(const std::array<CardMask,52>& g,CardMask pool,int k){
    int n=pop(pool);if(n<k)return 0;
    if(k==1)return n;
    uint64_t total=0;
    if(k==2){while(pool){int i=low(pool);pool&=pool-1;total+=pop(g[i]&pool);}return total;}
    while(pop(pool)>=k){int i=low(pool);pool&=pool-1;total+=cliques(g,pool&g[i],k-1);}
    return total;
}
// Reusable immutable table, keyed by exact physical board set, independent of hero.
class BoardRanks {
    CardMask board_=0;
    std::array<std::array<uint16_t,52>,52> pairs_{};
    uint16_t nuts_=0;
public:
    template<class RankTable> BoardRanks(const RankTable& rt,const std::vector<int>& b){
        if(b.size()<3||b.size()>5)throw std::invalid_argument("board size must be 3..5");
        for(int c:b){if(c<0||c>=52||(board_&(1ULL<<c)))throw std::invalid_argument("invalid board card");board_|=1ULL<<c;}
        for(int i=0;i<52;++i)if(!(board_&(1ULL<<i)))
            for(int j=i+1;j<52;++j)if(!(board_&(1ULL<<j))){
                uint16_t v=0;
                for(size_t x=0;x<b.size();++x)for(size_t y=x+1;y<b.size();++y)for(size_t z=y+1;z<b.size();++z)
                    v=std::max(v,rt.five({i,j,b[x],b[y],b[z]}));
                pairs_[i][j]=pairs_[j][i]=v;nuts_=std::max(nuts_,v);
            }
    }
    uint16_t pair(int i,int j) const {return pairs_.at(i).at(j);}
    RelativeStrength classify(const std::vector<int>& hero)const{
        if(hero.size()!=5)throw std::invalid_argument("PLO5 requires five hero cards");
        CardMask used=board_;for(int c:hero){if(c<0||c>=52||(used&(1ULL<<c)))throw std::invalid_argument("duplicate or invalid hero card");used|=1ULL<<c;}
        RelativeStrength r;r.board_nuts=nuts_;
        for(int i=0;i<5;++i)for(int j=i+1;j<5;++j)r.hero=std::max(r.hero,pairs_[hero[i]][hero[j]]);
        CardMask pool=((1ULL<<52)-1)&~used;
        std::array<CardMask,52> lt{},le{};int edges_lt=0,edges_le=0;
        for(CardMask p=pool;p;p&=p-1){int i=low(p);for(CardMask q=p&(p-1);q;q&=q-1){int j=low(q);auto v=pairs_[i][j];r.opponent_max=std::max(r.opponent_max,v);
            if(v<=r.hero){le[i]|=1ULL<<j;le[j]|=1ULL<<i;++edges_le;}
            if(v<r.hero){lt[i]|=1ULL<<j;lt[j]|=1ULL<<i;++edges_lt;}
        }}
        int n=pop(pool);uint64_t total=combinations(n,5);int edges=n*(n-1)/2;
        auto count=[&](const std::array<CardMask,52>& g,int e){return e==edges?total:e<10?uint64_t(0):cliques(g,pool,5);};
        r.wins=count(lt,edges_lt);uint64_t not_losing=edges_le==edges_lt?r.wins:count(le,edges_le);
        r.ties=not_losing-r.wins;r.losses=total-not_losing;return r;
    }
};
} // namespace plo5
