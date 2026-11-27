#define main rank_shard_cli_main
#include "plo5_rank_shard.cpp"
#undef main
#include <numeric>
namespace plo5 {
// Uniform unseen board cards only: no opponent ranges or showdown equity.
struct RunoutResult {
    uint16_t current=0;
    uint64_t total=0, improved=0, category_up=0;
    std::array<uint64_t,9> categories{};
    std::array<uint16_t,52> next_rank{};
    std::array<uint64_t,52> next_total{}, next_improved{};
    std::array<std::array<uint64_t,9>,52> next_categories{};
};
RunoutResult runouts(const RankTable& rt,const std::vector<int>& h,const std::vector<int>& b,const std::vector<int>& dead={}) {
    if(b.size()<3||b.size()>5) throw std::invalid_argument("postflop board required");
    auto matrix=CanonicalIndex::from_cards(h,b);
    U used=0; for(int c:h) used|=1ULL<<c; for(int c:b) used|=1ULL<<c;
    for(int c:dead){if(c<0||c>=52||(used&(1ULL<<c)))throw std::invalid_argument("invalid dead card");used|=1ULL<<c;}
    std::vector<int> pool;for(int c=0;c<52;++c)if(!(used&(1ULL<<c)))pool.push_back(c);
    if(pool.size()<5-b.size())throw std::invalid_argument("not enough unseen cards");
    RunoutResult r;r.current=rt.omaha(matrix);int cat=rt.category(r.current);
    auto triple=[&](int x,int y,int z){uint16_t best=0;for(int i=0;i<5;++i)for(int j=i+1;j<5;++j)best=std::max(best,rt.five({h[i],h[j],x,y,z}));return best;};
    auto record=[&](uint16_t v){++r.total;++r.categories[rt.category(v)];r.improved+=v>r.current;r.category_up+=rt.category(v)>cat;};
    auto conditional=[&](int c,uint16_t v){++r.next_total[c];++r.next_categories[c][rt.category(v)];r.next_improved[c]+=v>r.current;};
    if(b.size()==5){record(r.current);return r;}
    for(int x:pool){auto v=r.current;for(size_t i=0;i<b.size();++i)for(size_t j=i+1;j<b.size();++j)v=std::max(v,triple(b[i],b[j],x));r.next_rank[x]=v;}
    if(b.size()==4){for(int x:pool){record(r.next_rank[x]);conditional(x,r.next_rank[x]);}return r;}
    for(size_t i=0;i<pool.size();++i)for(size_t j=i+1;j<pool.size();++j){int x=pool[i],y=pool[j];auto v=std::max(r.next_rank[x],r.next_rank[y]);for(int z:b)v=std::max(v,triple(z,x,y));record(v);conditional(x,v);conditional(y,v);}
    return r;
}
static void verify(const RankTable& rt,const std::vector<int>& h,const std::vector<int>& b,const std::vector<int>& dead={}){
    auto r=runouts(rt,h,b,dead);std::vector<int> p;for(int c=0;c<52;++c)if(std::find(h.begin(),h.end(),c)==h.end()&&std::find(b.begin(),b.end(),c)==b.end()&&std::find(dead.begin(),dead.end(),c)==dead.end())p.push_back(c);
    RunoutResult e;e.current=rt.omaha(CanonicalIndex::from_cards(h,b));
    auto record=[&](std::vector<int> board,int first,int second){auto v=rt.omaha(CanonicalIndex::from_cards(h,board));++e.total;++e.categories[rt.category(v)];e.improved+=v>e.current;e.category_up+=rt.category(v)>rt.category(e.current);for(int c:{first,second})if(c>=0){++e.next_total[c];++e.next_categories[c][rt.category(v)];e.next_improved[c]+=v>e.current;}};
    if(b.size()==5)record(b,-1,-1);
    else for(size_t i=0;i<p.size();++i){auto t=b;t.push_back(p[i]);e.next_rank[p[i]]=rt.omaha(CanonicalIndex::from_cards(h,t));if(b.size()==4)record(t,p[i],-1);else for(size_t j=i+1;j<p.size();++j){auto f=t;f.push_back(p[j]);record(f,p[i],p[j]);}}
    if(r.total!=e.total||r.current!=e.current||r.categories!=e.categories||r.improved!=e.improved||r.category_up!=e.category_up||r.next_rank!=e.next_rank||r.next_total!=e.next_total||r.next_improved!=e.next_improved||r.next_categories!=e.next_categories)throw std::logic_error("runout mismatch");
}
}
int main(){try{RankTable rt;std::mt19937_64 rng(42);std::vector<int> deck(52);std::iota(deck.begin(),deck.end(),0);U outcomes=0;
for(int s:{3,4,5})for(int i=0;i<100;++i){std::shuffle(deck.begin(),deck.end(),rng);std::vector<int> h(deck.begin(),deck.begin()+5),b(deck.begin()+5,deck.begin()+5+s),dead(deck.begin()+5+s,deck.begin()+5+s+i%4);verify(rt,h,b,dead);auto r=runouts(rt,h,b,dead);outcomes+=r.total;for(int& c:h)c^=3;for(int& c:b)c^=3;for(int& c:dead)c^=3;auto t=runouts(rt,h,b,dead);if(t.categories!=r.categories||t.improved!=r.improved||t.current!=r.current)throw std::logic_error("suit symmetry mismatch");}
// Royal already made: all continuations have unchanged highest rank.
auto royal=runouts(rt,{48,44,1,6,11},{40,36,32});if(royal.total!=946||royal.improved||royal.categories[8]!=946)throw std::logic_error("royal mismatch");
bool rejected=false;try{runouts(rt,{48,44,1,6,11},{40,36,32},{48});}catch(const std::invalid_argument&){rejected=true;}if(!rejected)throw std::logic_error("invalid input accepted");
std::cout<<"PASS 300 scenarios, "<<outcomes<<" final boards cross-checked, 300 suit swaps, royal and invalid dead card\n";
for(int s:{3,4,5}){CanonicalIndex ix(s);U sum=0;auto start=std::chrono::steady_clock::now();for(int i=0;i<1000;++i){auto m=ix.unrank(rng()%ix.size());std::vector<int> h,b;for(int r=0;r<13;++r)for(int j=0;j<4;++j){if(m[r][j]==1)h.push_back(r*4+j);else if(m[r][j])b.push_back(r*4+j);}auto result=runouts(rt,h,b);sum+=result.improved;}double sec=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();std::cout<<"street="<<s<<" n=1000 seconds="<<sec<<" per_second="<<1000/sec<<" checksum="<<sum<<"\n";}
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
