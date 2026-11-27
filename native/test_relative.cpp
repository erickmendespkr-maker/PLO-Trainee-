#define main rank_shard_cli_main
#include "plo5_rank_shard.cpp"
#undef main
#include "plo5_relative_strength.hpp"
using namespace plo5;
// Independent exhaustive enumeration of every legal opposing five-card holding.
static std::array<U,3> brute(const BoardRanks& b,const std::vector<int>& h,const std::vector<int>& board,uint16_t rank){
    std::vector<int> p;for(int c=0;c<52;++c)if(std::find(h.begin(),h.end(),c)==h.end()&&std::find(board.begin(),board.end(),c)==board.end())p.push_back(c);
    std::array<U,3> out{};int n=p.size();for(int a=0;a<n;++a)for(int d=a+1;d<n;++d)for(int e=d+1;e<n;++e)for(int f=e+1;f<n;++f)for(int g=f+1;g<n;++g){int v[]={p[a],p[d],p[e],p[f],p[g]};uint16_t mx=0;for(int i=0;i<5;++i)for(int j=i+1;j<5;++j)mx=std::max(mx,b.pair(v[i],v[j]));++out[mx<rank?0:mx==rank?1:2];}return out;
}
int main(){RankTable rt;std::mt19937_64 rng(42);std::vector<int> deck(52);for(int i=0;i<52;++i)deck[i]=i;U outcomes=0,tests=0;
for(int street:{3,4,5}){for(int i=0;i<12;++i){std::shuffle(deck.begin(),deck.end(),rng);std::vector<int> b(deck.begin(),deck.begin()+street),h(deck.begin()+street,deck.begin()+street+5);BoardRanks br(rt,b);auto r=br.classify(h);auto v=brute(br,h,b,r.hero);assert((v==std::array<U,3>{r.wins,r.ties,r.losses}));assert(r.hero==rt.omaha(CanonicalIndex::from_cards(h,b)));assert(r.cannot_lose_now()==(r.hero>=r.opponent_max));outcomes+=r.wins+r.ties+r.losses;++tests;}}
// Royal flush with exactly two hole cards, no opponent can tie.
{std::vector<int> h={48,44,1,6,11},b={40,36,32,3,9};BoardRanks br(rt,b);auto r=br.classify(h);assert(r.hero==7462&&r.absolute_nuts()&&r.wins==850668&&r.ties==0&&r.losses==0);}
{BoardRanks br(rt,{0,1,2});bool rejected=false;try{br.classify({0,4,5,6,7});}catch(const std::invalid_argument&){rejected=true;}assert(rejected);}
std::cout<<"PASS exhaustive opponent enumeration: "<<tests<<" scenarios, "<<outcomes<<" holdings; royal and invalid input checks\n";
for(int s:{3,4,5}){std::shuffle(deck.begin(),deck.end(),rng);std::vector<int> b(deck.begin(),deck.begin()+s),p(deck.begin()+s,deck.end());BoardRanks br(rt,b);U checksum=0;auto t=std::chrono::steady_clock::now();for(int i=0;i<10000;++i){std::shuffle(p.begin(),p.end(),rng);auto r=br.classify(std::vector<int>(p.begin(),p.begin()+5));checksum+=r.wins+r.ties;}double sec=std::chrono::duration<double>(std::chrono::steady_clock::now()-t).count();std::cout<<"street="<<s<<" n=10000 seconds="<<sec<<" per_second="<<10000/sec<<" checksum="<<checksum<<"\n";}
}
