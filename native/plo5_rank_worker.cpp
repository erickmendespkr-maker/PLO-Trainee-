// Persistent bounded offline canonical index and exact Omaha rank service.
#define main plo5_rank_shard_main
#include "plo5_rank_shard.cpp"
#undef main
#include <memory>
int main(){try{
 std::ios::sync_with_stdio(false);std::cin.tie(nullptr);
 std::array<std::unique_ptr<CanonicalIndex>,6> indexes;
 std::unique_ptr<RankTable> ranks;
 int street,n;
 while(std::cin>>street){
  if(!(std::cin>>n)||street<3||street>5||n<1||n>4096)throw std::runtime_error("invalid request");
  if(!indexes[street])indexes[street]=std::make_unique<CanonicalIndex>(street);
  std::vector<std::pair<U,uint16_t>> output;output.reserve(n);
  if(!ranks)ranks=std::make_unique<RankTable>();
  for(int i=0;i<n;++i){
   std::vector<int> h(5),b(street);
   for(int& x:h)if(!(std::cin>>x))throw std::runtime_error("missing hand");
   for(int& x:b)if(!(std::cin>>x))throw std::runtime_error("missing board");
   auto m=CanonicalIndex::from_cards(h,b);
   output.emplace_back(indexes[street]->rank(m),ranks->omaha(m));
  }
  std::cout<<"OK "<<n<<'\n';for(auto x:output)std::cout<<x.first<<' '<<x.second<<'\n';
  std::cout.flush();if(!std::cout)throw std::runtime_error("output failure");
 }
 if(!std::cin.eof())throw std::runtime_error("invalid input");
 return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
