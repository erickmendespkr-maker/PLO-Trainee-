// Native offline PLO5 fixed-holding multiway Monte Carlo.
// Reuses the exact existing five-card rank table; deterministic per trial,
// independent of thread scheduling. No strategic inference or rake.
#define main rank_shard_cli_main
#include "plo5_rank_shard.cpp"
#undef main
#include <thread>
#include <numeric>

struct EquityResult {
    std::vector<U> units;
    U trials=0;
};
static U mix(U x) {
    x+=0x9e3779b97f4a7c15ULL;
    x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;
    x=(x^(x>>27))*0x94d049bb133111ebULL;
    return x^(x>>31);
}
static EquityResult simulate(const RankTable& rt,const std::vector<std::vector<int>>& hands,U trials,U seed_value,int threads){
    if(hands.size()<2||hands.size()>6||!trials||trials>10000000||threads<1||threads>32)
        throw std::invalid_argument("invalid equity budget or seats");
    U used=0;
    for(auto& h:hands){
        if(h.size()!=5)throw std::invalid_argument("five cards required");
        for(int c:h){
            if(c<0||c>=52||(used&(1ULL<<c)))throw std::invalid_argument("invalid or duplicate card");
            used|=1ULL<<c;
        }
    }
    std::vector<int> pool;
    for(int c=0;c<52;++c)if(!(used&(1ULL<<c)))pool.push_back(c);
    size_t n=hands.size();
    threads=int(std::min<U>(trials,threads));
    std::vector<std::vector<U>> partial(threads,std::vector<U>(n));
    auto worker=[&](int t){
        for(U k=t;k<trials;k+=threads){
            std::mt19937_64 rng(mix(seed_value+k));
            auto deck=pool;
            for(int j=0;j<5;++j){
                std::uniform_int_distribution<int> dist(j,int(deck.size())-1);
                std::swap(deck[j],deck[dist(rng)]);
            }
            std::array<uint16_t,6> ranks{};
            uint16_t best=0;
            for(size_t p=0;p<n;++p){
                const auto& h=hands[p];
                for(int i=0;i<5;++i)for(int j=i+1;j<5;++j)
                    for(int a=0;a<5;++a)for(int b=a+1;b<5;++b)for(int c=b+1;c<5;++c)
                        ranks[p]=std::max(ranks[p],rt.five({h[i],h[j],deck[a],deck[b],deck[c]}));
                best=std::max(best,ranks[p]);
            }
            int count=0;for(size_t p=0;p<n;++p)count+=ranks[p]==best;
            for(size_t p=0;p<n;++p)if(ranks[p]==best)partial[t][p]+=60/count;
        }
    };
    std::vector<std::thread> workers;
    try{for(int t=1;t<threads;++t)workers.emplace_back(worker,t);worker(0);}
    catch(...){for(auto& w:workers)if(w.joinable())w.join();throw;}
    for(auto& w:workers)w.join();
    EquityResult r{std::vector<U>(n),trials};
    for(auto& v:partial)for(size_t p=0;p<n;++p)r.units[p]+=v[p];
    if(std::accumulate(r.units.begin(),r.units.end(),U(0))!=60*trials)throw std::logic_error("equity conservation");
    return r;
}
int main(int argc,char** argv){try{
    RankTable rt;
    if(argc==2&&std::string(argv[1])=="test"){
        std::vector<std::vector<int>> h={{0,5,10,15,20},{25,30,35,40,45}};
        auto a=simulate(rt,h,1000,42,1),b=simulate(rt,h,1000,42,4);
        if(a.units!=b.units)throw std::logic_error("thread reproducibility");
        std::vector<std::vector<int>> six;
        for(int i=0;i<6;++i){std::vector<int> row;for(int j=0;j<5;++j)row.push_back(i*5+j);six.push_back(row);}
        simulate(rt,six,1000,42,2);
        bool rejected=false;try{simulate(rt,{h[0],h[0]},1,42,1);}catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::logic_error("blocker validation");
        for(int t:{1,2,4}){
            auto start=std::chrono::steady_clock::now();auto r=simulate(rt,h,10000,42,t);
            double secs=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
            std::cout<<"threads="<<t<<" trials=10000 seconds="<<secs<<" trials_per_second="<<10000/secs<<" checksum="<<r.units[0]<<"\n";
        }
        std::cout<<"PASS native equity checks\n";return 0;
    }
    // Persistent process: one shared rank table for multiple queries.
    if(argc!=2||std::string(argv[1])!="stream")throw std::invalid_argument("test | stream");
    U trials,seed_value;int threads,n;
    while(std::cin>>trials>>seed_value>>threads>>n){
        if(n<2||n>6)throw std::invalid_argument("invalid seats");
        std::vector<std::vector<int>> h(n,std::vector<int>(5));
        for(auto& row:h)for(int& c:row)if(!(std::cin>>c))throw std::invalid_argument("truncated holding");
        auto r=simulate(rt,h,trials,seed_value,threads);
        std::cout<<r.trials;for(U x:r.units)std::cout<<" "<<x;std::cout<<std::endl;
    }
    if(!std::cin.eof())throw std::invalid_argument("invalid stream");
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
