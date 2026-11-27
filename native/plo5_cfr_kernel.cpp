// Restricted HU CFR+ numeric kernel; game tree supplied by caller.
#include <vector>
#include <algorithm>
#include <stdexcept>
#include <cmath>
#include <iostream>
#include <cassert>
struct Info { std::vector<double> regret, average; };
struct Node { int actor; std::vector<int> children; std::vector<int> infos; double offset=0, slope=0; };
struct Deal { double weight, equity; };
struct Kernel {
 std::vector<std::vector<double>> continuation;
 std::vector<Node> nodes; std::vector<Deal> deals; std::vector<Info> info;
 std::vector<std::vector<double>> policy,delta;
 static std::vector<double> normalize(const std::vector<double>& v){double sum=0;for(double x:v)sum+=x;auto p=v;for(auto& x:p)x=sum?x/sum:1.0/p.size();return p;}
 double walk(int n,int d,double r0,double r1,int t){const auto& a=nodes[n];const auto& z=deals[d];if(a.actor<0)return !continuation.empty()&&!continuation[n].empty()?continuation[n][d]:a.offset+a.slope*z.equity;int k=a.infos[d];const auto& p=policy[k];std::vector<double> v(p.size());double mean=0;for(size_t j=0;j<p.size();++j){v[j]=walk(a.children[j],d,r0*(a.actor==0?p[j]:1),r1*(a.actor==1?p[j]:1),t);mean+=p[j]*v[j];}for(size_t j=0;j<p.size();++j){delta[k][j]+=z.weight*(a.actor==0?r1:-r0)*(v[j]-mean);info[k].average[j]+=t*z.weight*(a.actor==0?r0:r1)*p[j];}return mean;}
 void run(int iterations){for(int t=1;t<=iterations;++t){policy.clear();delta.clear();for(auto& i:info){policy.push_back(normalize(i.regret));delta.emplace_back(i.regret.size(),0);}for(size_t d=0;d<deals.size();++d)walk(0,d,1,1,t);for(size_t k=0;k<info.size();++k)for(size_t j=0;j<delta[k].size();++j)info[k].regret[j]=std::max(0.0,info[k].regret[j]+delta[k][j]);}}
};
int main(){for(int i=0;i<=20;++i){double q=i/20.0;Kernel k;k.nodes={{0,{1,2},{0}},{-1,{},{},-.5,0},{-1,{},{},-1,2}};k.deals={{1,q}};k.info={{{0,0},{0,0}}};k.run(500);auto p=Kernel::normalize(k.info[0].average);double v=-.5*p[0]+(2*q-1)*p[1];assert(std::abs(v-std::max(-.5,2*q-1))<.01);}std::cout<<"PASS 21 analytical HU fixtures\n";return 0;}
