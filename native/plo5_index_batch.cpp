// Bounded batch interface to the existing canonical PLO5 index.
#include "plo5_canonical_index.hpp"
#include <iostream>
#include <memory>
#include <random>
#include <string>
int main(){try{
 int street,n;std::string mode;
 if(!(std::cin>>street>>mode>>n)||n<0||n>1000000)throw std::runtime_error("invalid batch");
 auto idx=std::make_unique<plo5::CanonicalIndex>(street);
 if(mode=="size"&&n==0)std::cout<<idx->size()<<'\n';
 else if(mode=="rank")for(int i=0;i<n;++i){
  std::vector<int> h(5),b(street);for(int& x:h)if(!(std::cin>>x))throw std::runtime_error("missing hand");
  for(int& x:b)if(!(std::cin>>x))throw std::runtime_error("missing board");
  std::cout<<idx->rank(plo5::CanonicalIndex::from_cards(h,b))<<'\n';
 }else if(mode=="unrank")for(int i=0;i<n;++i){
  uint64_t k;if(!(std::cin>>k))throw std::runtime_error("missing id");auto m=idx->unrank(k);
  for(auto row:m)for(auto v:row)std::cout<<int(v);
  std::cout<<'\n';
 }else if(mode=="audit"){
  std::mt19937_64 rng(27112026);for(int i=0;i<n;++i){uint64_t k=i==0?0:i==1?idx->size()-1:rng()%idx->size();if(idx->rank(idx->unrank(k))!=k)throw std::runtime_error("roundtrip");}
  std::cout<<idx->size()<<' '<<n<<'\n';
 }else throw std::runtime_error("invalid mode");
 std::string extra;if(std::cin>>extra)throw std::runtime_error("extra input");return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
