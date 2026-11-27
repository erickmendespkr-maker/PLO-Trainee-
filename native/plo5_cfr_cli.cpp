// Bounded text protocol for native HU CFR+ training.
#define main kernel_selftest_main
#include "plo5_cfr_kernel.cpp"
#undef main
#include <iomanip>
#include <numeric>
int main(){try{
 int n,d,k,t;
 if(!(std::cin>>n>>d>>k>>t)||n<1||n>10000||d<1||d>4096||k<1||k>1000000||t<1||t>50000||1LL*n*d*t>100000000)throw std::runtime_error("budget");
 Kernel x;x.nodes.resize(n);x.info.resize(k);x.deals.resize(d);
 double mass=0;
 for(auto& z:x.deals){if(!(std::cin>>z.weight>>z.equity)||!std::isfinite(z.weight)||z.weight<=0||!std::isfinite(z.equity)||z.equity<0||z.equity>1)throw std::runtime_error("deal");mass+=z.weight;}
 if(std::abs(mass-1)>1e-8)throw std::runtime_error("mass");
 std::vector<int> parents(n),owner(k,-1),used(k);
 for(int i=0;i<n;++i){
 auto& a=x.nodes[i];int count;
 if(!(std::cin>>a.actor>>count>>a.offset>>a.slope)||a.actor< -1||a.actor>1||count<0||count>1024||!std::isfinite(a.offset)||!std::isfinite(a.slope))throw std::runtime_error("node");
 if(a.actor==-1){if(count)throw std::runtime_error("terminal");continue;}
 if(count<1)throw std::runtime_error("actions");
 a.children.resize(count);a.infos.resize(d);
 for(int& c:a.children){if(!(std::cin>>c)||c<=i||c>=n||++parents[c]!=1)throw std::runtime_error("tree");}
 for(int& j:a.infos){if(!(std::cin>>j)||j<0||j>=k)throw std::runtime_error("info");if(owner[j]<0){owner[j]=i;x.info[j].regret.assign(count,0);x.info[j].average.assign(count,0);}if(owner[j]!=i)throw std::runtime_error("shared info across nodes");used[j]=1;}
 }
 for(int i=1;i<n;++i)if(parents[i]!=1)throw std::runtime_error("unreachable");
 for(int j:used)if(!j)throw std::runtime_error("unused info");
 std::string extra;
 if(std::cin>>extra){
  if(extra!="CONT1")throw std::runtime_error("extra input");
  int count;if(!(std::cin>>count)||count<0||count>n||1LL*count*d>2000000)throw std::runtime_error("continuation budget");
  x.continuation.resize(n);
  for(int j=0;j<count;++j){
   int id;if(!(std::cin>>id)||id<0||id>=n||x.nodes[id].actor!=-1||!x.continuation[id].empty())throw std::runtime_error("continuation node");
   auto& v=x.continuation[id];v.resize(d);
   for(double& a:v)if(!(std::cin>>a)||!std::isfinite(a)||std::abs(a)>1e12)throw std::runtime_error("continuation value");
  }
  if(std::cin>>extra)throw std::runtime_error("extra input");
 }
 x.run(t);std::cout<<std::setprecision(17);
 for(int j=0;j<k;++j){std::cout<<j;for(double p:Kernel::normalize(x.info[j].average))std::cout<<" "<<p;std::cout<<"\n";}
 return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
