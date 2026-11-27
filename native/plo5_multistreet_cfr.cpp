// Offline two-utility CFR+ over a forest of hidden chance scenarios.
// Info IDs are shared across scenarios by the caller's public/private infosets.
#include <algorithm>
#include <array>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <vector>
using Pay=std::array<double,2>;
struct Info{std::vector<double> regret,avg,policy,delta;};
struct Node{int actor=-1,id=-1;Pay pay{};std::vector<int> children;};
void require(bool ok,const char* msg){if(!ok)throw std::runtime_error(msg);}
int main(){try{
 int n,k,d,t;require(bool(std::cin>>n>>k>>d>>t)&&n>0&&n<=1000000&&k>0&&k<=1000000&&d>0&&d<=155648&&t>0&&t<=50000&&1LL*n*t<=100000000,"budget");
 std::vector<Node> nodes(n);std::vector<Info> infos(k);std::vector<int> roots(d),parents(n),depth(n);std::vector<double> weights(d);double mass=0;
 for(int i=0;i<d;++i){require(bool(std::cin>>roots[i]>>weights[i])&&roots[i]>=0&&roots[i]<n&&std::isfinite(weights[i])&&weights[i]>0&&++parents[roots[i]]==1,"root");mass+=weights[i];}
 require(std::abs(mass-1)<1e-8,"mass");
 for(int i=0;i<n;++i){auto& a=nodes[i];require(bool(std::cin>>a.actor)&&a.actor>=-1&&a.actor<=1,"actor");
  require(parents[i]==1,"unreachable");
  if(a.actor<0){require(bool(std::cin>>a.pay[0]>>a.pay[1])&&std::isfinite(a.pay[0])&&std::isfinite(a.pay[1])&&std::abs(a.pay[0])<=1e13&&std::abs(a.pay[1])<=1e13,"terminal");continue;}
  int count;require(bool(std::cin>>a.id>>count)&&a.id>=0&&a.id<k&&count>=1&&count<=20,"info");
  auto& f=infos[a.id];if(f.regret.empty()){f.regret.resize(count);f.avg.resize(count);f.policy.resize(count);f.delta.resize(count);}require(int(f.regret.size())==count,"info shape");
  a.children.resize(count);for(int& child:a.children){require(bool(std::cin>>child)&&child>i&&child<n&&++parents[child]==1,"tree");depth[child]=depth[i]+1;require(depth[child]<=128,"depth");}
 }
 for(auto& f:infos){require(!f.regret.empty(),"unused info");}
 std::string extra;require(!(std::cin>>extra),"extra input");
 auto walk=[&](auto&& self,int i,double w,double r0,double r1,int iter)->Pay{
  const auto& a=nodes[i];if(a.actor<0)return a.pay;auto& f=infos[a.id];Pay mean{};std::array<Pay,20> vals{};
  for(size_t j=0;j<a.children.size();++j){double p=f.policy[j];vals[j]=self(self,a.children[j],w,r0*(a.actor==0?p:1),r1*(a.actor==1?p:1),iter);for(int z=0;z<2;++z)mean[z]+=p*vals[j][z];}
  for(size_t j=0;j<a.children.size();++j){f.delta[j]+=w*(a.actor==0?r1:r0)*(vals[j][a.actor]-mean[a.actor]);f.avg[j]+=iter*w*(a.actor==0?r0:r1)*f.policy[j];}return mean;
 };
 for(int iter=1;iter<=t;++iter){for(auto& f:infos){double z=0;for(double v:f.regret)z+=v;for(size_t j=0;j<f.regret.size();++j){f.policy[j]=z?f.regret[j]/z:1.0/f.regret.size();f.delta[j]=0;}}
  for(int i=0;i<d;++i)walk(walk,roots[i],weights[i],1,1,iter);
  for(auto& f:infos)for(size_t j=0;j<f.regret.size();++j)f.regret[j]=std::max(0.0,f.regret[j]+f.delta[j]);}
 std::cout<<std::setprecision(17);for(int i=0;i<k;++i){auto& f=infos[i];double z=0;for(double v:f.avg)z+=v;std::cout<<i;for(double v:f.avg)std::cout<<' '<<(z?v/z:1.0/f.avg.size());std::cout<<'\n';}return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
