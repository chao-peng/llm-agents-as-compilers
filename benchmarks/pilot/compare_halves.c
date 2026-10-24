#include <stdint.h>
#include <stddef.h>
#include <string.h>

uint64_t kernel(const uint64_t *a, size_t n, uint64_t x) {
    size_t m=n/2; int r=memcmp(a,a+m,m*sizeof(uint64_t)); return r<0?0:r>0?2:1;
}
