#include "plo5_canonical_index.hpp"
#include <cassert>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <random>
#include <string>
namespace fs=std::filesystem;
using namespace plo5;
using U=uint64_t;
// Exact five-card high rank. Categories ascending, followed by kickers.
static uint32_t score(const std::array<int,5>& a) {
    int n[13]={}, suits[4]={}, mask=0;
    for(int c:a){++n[c/4];++suits[c%4];mask|=1<<(c/4);}
    int st=-1; for(int r=12;r>=4;--r) if((mask&(31<<(r-4)))==(31<<(r-4))){st=r;break;}
    if(st<0 && (mask&0x100f)==0x100f) st=3;
    bool flush=*std::max_element(suits,suits+4)==5;
    int four=-1,three=-1,p[2]={-1,-1},np=0,s[5]={},ns=0;
    for(int r=12;r>=0;--r) switch(n[r]){case 4:four=r;break;case 3:three=r;break;case 2:p[np++]=r;break;case 1:s[ns++]=r;break;}
    auto enc=[](int cat,int a=0,int b=0,int c=0,int d=0,int e=0){return uint32_t((cat<<20)|(a<<16)|(b<<12)|(c<<8)|(d<<4)|e);};
    if(flush && st>=0)return enc(8,st);
    if(four>=0)return enc(7,four,s[0]);
    if(three>=0 && np)return enc(6,three,p[0]);
    if(flush)return enc(5,s[0],s[1],s[2],s[3],s[4]);
    if(st>=0)return enc(4,st);
    if(three>=0)return enc(3,three,s[0],s[1]);
    if(np==2)return enc(2,p[0],p[1],s[0]);
    if(np==1)return enc(1,p[0],s[0],s[1],s[2]);
    return enc(0,s[0],s[1],s[2],s[3],s[4]);
}
class RankTable {
    uint32_t choose[53][6]{};
    std::vector<uint16_t> table;
    std::vector<uint32_t> codes;
public:
    std::array<U,9> hist{};
    RankTable(){
        for(int n=0;n<=52;++n){choose[n][0]=1;for(int k=1;k<=5 && k<=n;++k)choose[n][k]=choose[n-1][k-1]+choose[n-1][k];}
        std::vector<uint32_t> raw(choose[52][5]);
        for(int e=4;e<52;++e)for(int d=3;d<e;++d)for(int c=2;c<d;++c)for(int b=1;b<c;++b)for(int a=0;a<b;++a){
            std::array<int,5> x={a,b,c,d,e}; auto v=score(x);raw[offset(x)]=v;++hist[v>>20];
        }
        codes=raw;std::sort(codes.begin(),codes.end());codes.erase(std::unique(codes.begin(),codes.end()),codes.end());
        if(codes.size()!=7462)throw std::logic_error("rank universe mismatch");
        table.resize(raw.size());for(size_t i=0;i<raw.size();++i)table[i]=uint16_t(1+std::lower_bound(codes.begin(),codes.end(),raw[i])-codes.begin());
    }
    uint32_t offset(std::array<int,5> a)const{std::sort(a.begin(),a.end());return choose[a[0]][1]+choose[a[1]][2]+choose[a[2]][3]+choose[a[3]][4]+choose[a[4]][5];}
    uint16_t five(std::array<int,5> a)const{return table[offset(a)];}
    int category(uint16_t r)const{return codes.at(r-1)>>20;}
    uint16_t omaha(const Matrix& m)const{
        int h[5],b[5],nh=0,nb=0;for(int r=0;r<13;++r)for(int s=0;s<4;++s){if(m[r][s]==1)h[nh++]=r*4+s;else if(m[r][s])b[nb++]=r*4+s;}
        uint16_t best=0;for(int i=0;i<5;++i)for(int j=i+1;j<5;++j)for(int x=0;x<nb;++x)for(int y=x+1;y<nb;++y)for(int z=y+1;z<nb;++z)best=std::max(best,five({h[i],h[j],b[x],b[y],b[z]}));return best;
    }
};
// Binary format: 8 magic bytes, street/start/count/checksum as LE u64, then LE u16 ranks.
static void put(std::ostream& f,U v,int n){for(int i=0;i<n;++i)f.put(char((v>>(8*i))&255));}
static U get(std::istream& f,int n){U v=0;for(int i=0;i<n;++i){int c=f.get();if(c<0)throw std::runtime_error("truncated shard");v|=U(c)<<(8*i);}return v;}
static U digest(U hash,U value,int n){for(int i=0;i<n;++i){hash^=(value>>(8*i))&255;hash*=1099511628211ULL;}return hash;}
static constexpr U seed=14695981039346656037ULL, limit=10000000;
static void bounds(int street,U start,U count){if(street<3||street>5||!count||count>limit)throw std::invalid_argument("invalid street or shard count (1..10000000)");CanonicalIndex ix(street);if(start>=ix.size()||count>ix.size()-start)throw std::out_of_range("shard outside index");}
static void generate(int street,U start,U count,const fs::path& path){
    bounds(street,start,count);if(fs::exists(path)||fs::exists(path.string()+".tmp"))throw std::runtime_error("output already exists");
    CanonicalIndex ix(street);RankTable rt;auto t=std::chrono::steady_clock::now();
    auto temp=path.string()+".tmp";std::ofstream f(temp,std::ios::binary);if(!f)throw std::runtime_error("cannot open output");
    f.write("P5RANK01",8);put(f,street,8);put(f,start,8);put(f,count,8);put(f,0,8);
    U hash=digest(digest(digest(seed,street,8),start,8),count,8);
    for(U i=0;i<count;++i){auto v=rt.omaha(ix.unrank(start+i));put(f,v,2);hash=digest(hash,v,2);}
    f.seekp(32);put(f,hash,8);f.close();if(!f)throw std::runtime_error("write failed");fs::rename(temp,path);
    double secs=std::chrono::duration<double>(std::chrono::steady_clock::now()-t).count();std::cout<<"street="<<street<<" count="<<count<<" seconds="<<secs<<" per_second="<<count/secs<<" bytes="<<fs::file_size(path)<<"\n";
}
static void inspect(const fs::path& path,U id){
    std::ifstream f(path,std::ios::binary);char magic[8];if(!f.read(magic,8)||std::string(magic,8)!="P5RANK01")throw std::runtime_error("invalid shard format");
    U s=get(f,8),start=get(f,8),count=get(f,8),expected=get(f,8);if(s>5)throw std::runtime_error("invalid street");bounds(int(s),start,count);
    if(id<start||id-start>=count)throw std::out_of_range("index not present in shard");
    U hash=digest(digest(digest(seed,s,8),start,8),count,8),answer=0;
    for(U i=0;i<count;++i){U v=get(f,2);if(v<1||v>7462)throw std::runtime_error("invalid rank");hash=digest(hash,v,2);if(i==id-start)answer=v;}
    if(f.peek()!=EOF||hash!=expected)throw std::runtime_error("shard integrity failure");
    std::cout<<"street="<<s<<" index="<<id<<" rank="<<answer<<" verified=1\n";
}
static void test(){
    RankTable rt;assert((rt.hist==std::array<U,9>{1302540,1098240,123552,54912,10200,5108,3744,624,40}));
    assert(rt.five({32,36,40,44,48})==7462);assert(rt.category(rt.five({48,0,4,8,12}))==8);
    assert(rt.five({48,0,4,8,12})<rt.five({0,4,8,12,16}));
    std::mt19937_64 rng(42);for(int s:{3,4,5}){CanonicalIndex ix(s);for(int i=0;i<10000;++i){U id=rng()%ix.size();auto m=ix.unrank(id);assert(ix.rank(m)==id);auto rank=rt.omaha(m);assert(rank>=1&&rank<=7462);for(auto& row:m)std::swap(row[0],row[3]);assert(rt.omaha(m)==rank);}}
    // Four royal board cards cannot be played as four community cards in Omaha.
    auto m=CanonicalIndex::from_cards({0,5,10,15,21},{32,36,40,44,48});assert(rt.category(rt.omaha(m))<8);
    std::cout<<"PASS: 2598960 five-card category census; 7462 rank levels; 30000 roundtrips and suit swaps; exact-two/exact-three check\n";
}
int main(int argc,char** argv){try{
    if(argc==2&&std::string(argv[1])=="test"){test();return 0;}
    if(argc==6&&std::string(argv[1])=="generate"){generate(std::stoi(argv[2]),std::stoull(argv[3]),std::stoull(argv[4]),argv[5]);return 0;}
    if(argc==4&&std::string(argv[1])=="inspect"){inspect(argv[2],std::stoull(argv[3]));return 0;}
    throw std::invalid_argument("test | generate STREET START COUNT FILE | inspect FILE INDEX");
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
