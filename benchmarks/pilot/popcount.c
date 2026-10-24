#include <stdint.h>
#include <stddef.h>

uint64_t kernel(const uint64_t *a, size_t n, uint64_t x) {
    uint64_t r=0; while(x) { r += x & 1; x >>= 1; } return r;
}
