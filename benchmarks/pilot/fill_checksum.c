#include <stdint.h>
#include <stddef.h>
#include <string.h>

uint64_t kernel(const uint64_t *a, size_t n, uint64_t x) {
    unsigned char b[256]; size_t m=n<256?n:256; memset(b,(int)(x & 255),m); uint64_t r=0; for(size_t i=0;i<m;++i) r+=b[i]; return r;
}
