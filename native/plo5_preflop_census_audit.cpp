#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <set>
#include <vector>
#include <chrono>
int main(){auto t=std::chrono::steady_clock::now();std::set<uint64_t> classes;uint64_t total=0;for(int a=0;a<52;++a)for(int b=a+1;b<52;++b)for(int c=b+1;c<52;++c)for(int d=c+1;d<52;++d)for(int e=d+1;e<52;++e){std::array<int,4> col{};for(int x:{a,b,c,d,e})col[x%4]|=1<<(12-x/4);std::sort(col.begin(),col.end());uint64_t key=0;for(auto v:col)key=(key<<13)|v;classes.insert(key);++total;}std::cout<<"physical="<<total<<" canonical="<<classes.size()<<" seconds="<<std::chrono::duration<double>(std::chrono::steady_clock::now()-t).count()<<'\n';return total==2598960&&classes.size()==134459?0:1;}
