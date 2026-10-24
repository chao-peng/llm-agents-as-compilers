#include <stdint.h>
#include <stddef.h>

uint64_t kernel(const uint64_t *a, size_t n, uint64_t x) {
    return x * (n + 1);
}
