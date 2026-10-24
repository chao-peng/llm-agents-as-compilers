#include <stdint.h>
#include <stddef.h>
#include <string.h>

uint64_t kernel(const uint64_t *a, size_t n, uint64_t x) {
    uint64_t b[256]; size_t m=n<256?n:256; memcpy(b,a,m*sizeof(uint64_t)); uint64_t r=x; for(size_t i=0;i<m;++i) r+=b[i]; return r;
}
