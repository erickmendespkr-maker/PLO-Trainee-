// Enumerate contiguous ranges of the existing dense preflop canonical IDs.
// Output: id, physical orbit multiplicity, five rank-major card IDs.
#include "plo5_canonical_index.hpp"
#include <iostream>
#include <string>
#include <set>
#include <numeric>
int main(int argc,char** argv){try{
    plo5::CanonicalIndex ix(0);
    if(ix.size()!=134459)throw std::logic_error("preflop universe mismatch");
    if(argc!=3)throw std::invalid_argument("START COUNT");
    auto start=std::stoull(argv[1]),count=std::stoull(argv[2]);
    if(!count||start>=ix.size()||count>ix.size()-start)throw std::out_of_range("invalid interval");
    uint64_t mass=0;
    for(uint64_t id=start;id<start+count;++id){
        auto m=ix.unrank(id);
        if(ix.rank(m)!=id)throw std::logic_error("roundtrip failed");
        std::vector<int> h;
        for(int r=0;r<13;++r)for(int s=0;s<4;++s)if(m[r][s])h.push_back(r*4+s);
        std::array<int,4> p={0,1,2,3};std::set<uint64_t> orbit;
        do{uint64_t mask=0;for(int c:h)mask|=1ULL<<(4*(c/4)+p[c%4]);orbit.insert(mask);}
        while(std::next_permutation(p.begin(),p.end()));
        mass+=orbit.size();
        std::cout<<id<<" "<<orbit.size();for(int c:h)std::cout<<" "<<c;std::cout<<"\n";
    }
    if(start==0&&count==ix.size()&&mass!=2598960)throw std::logic_error("orbit mass mismatch");
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
