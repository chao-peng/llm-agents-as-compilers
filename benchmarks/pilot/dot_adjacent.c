#include <stdint.h>
#include <stddef.h>

uint64_t kernel(const uint64_t *a, size_t n, uint64_t x) {
    uint64_t r = x; for (size_t i=1; i<n; ++i) r += a[i-1]*a[i]; return r;
}
