#include <stdint.h>
#include <stddef.h>

uint64_t kernel(const uint64_t *a, size_t n, uint64_t x) {
    uint64_t b=n; while(b) { uint64_t t=x%b; x=b; b=t; } return x;
}
