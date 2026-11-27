// Reuse the exact P5RANK01 evaluator for sparse misses without writing shards.
#define main plo5_rank_shard_main
#include "plo5_rank_shard.cpp"
#undef main
#include <memory>
int main(){try{
 int street,n;if(!(std::cin>>street>>n)||street<3||street>5||n<0||n>100000)throw std::runtime_error("invalid rank batch");
 auto idx=std::make_unique<CanonicalIndex>(street);std::vector<U> ids(n);
 for(auto& id:ids)if(!(std::cin>>id)||id>=idx->size())throw std::runtime_error("invalid index");
 std::string extra;if(std::cin>>extra)throw std::runtime_error("extra input");
 if(ids.empty())return 0;
 RankTable ranks;for(U id:ids)std::cout<<ranks.omaha(idx->unrank(id))<<'\n';return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
