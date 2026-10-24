#include <stdint.h>
#include <stddef.h>

uint64_t kernel(const uint64_t *a, size_t n, uint64_t x) {
    uint64_t b[256]; size_t m=n<256?n:256; for(size_t i=0;i<m;++i) b[i]=a[i]; for(size_t i=1;i<m;++i) { uint64_t v=b[i]; size_t j=i; while(j && b[j-1]>v) { b[j]=b[j-1]; --j; } b[j]=v; } uint64_t r=x; for(size_t i=0;i<m;++i) r=r*33+b[i]; return r;
}
