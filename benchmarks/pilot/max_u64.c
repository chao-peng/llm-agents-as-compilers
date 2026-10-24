#include <stdint.h>
#include <stddef.h>

uint64_t kernel(const uint64_t *a, size_t n, uint64_t x) {
    uint64_t r = x; for (size_t i=0; i<n; ++i) if (a[i]>r) r=a[i]; return r;
}
