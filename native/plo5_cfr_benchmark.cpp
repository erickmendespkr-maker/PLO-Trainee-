#define main kernel_selftest_main
#include "plo5_cfr_kernel.cpp"
#undef main
#include <chrono>
#include <iomanip>
#include <cstdlib>
int main(int argc,char**argv){
 int count=argc>1?std::atoi(argv[1]):256, iterations=argc>2?std::atoi(argv[2]):1000;
 if(count<1||count>4096||iterations<1||iterations>50000)return 2;
 Kernel k; k.nodes={{0,{1,2},{}},{-1,{},{},-.5,0},{1,{3,4},{}},{-1,{},{},1,0},{-1,{},{},-2,4}};
 for(int i=0;i<32;++i)k.info.push_back({{0,0},{0,0}});
 for(int d=0;d<count;++d){k.deals.push_back({1.0/count,((d*37)%101)/100.0});k.nodes[0].infos.push_back(d%16);k.nodes[2].infos.push_back(16+(d/16)%16);}
 auto t=std::chrono::steady_clock::now();k.run(iterations);double sec=std::chrono::duration<double>(std::chrono::steady_clock::now()-t).count();
 double checksum=0;for(size_t i=0;i<k.info.size();++i)checksum+=(i+1)*Kernel::normalize(k.info[i].average)[0];
 std::cout<<std::setprecision(12)<<"deals="<<count<<" iterations="<<iterations<<" node_visits="<<5LL*count*iterations<<" seconds="<<sec<<" visits_per_second="<<5.0*count*iterations/sec<<" checksum="<<checksum<<'\n';
}
