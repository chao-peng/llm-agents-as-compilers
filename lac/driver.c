#define _POSIX_C_SOURCE 200809L
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

extern uint64_t kernel(const uint64_t *, size_t, uint64_t);
static volatile uint64_t sink;

static uint64_t nanos(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) exit(3);
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}

int main(int argc, char **argv) {
    size_t n;
    uint64_t x;
    if (scanf("%zu %" SCNu64, &n, &x) != 2 || n > 1048576) return 2;
    uint64_t *storage = calloc(n + 2, sizeof(uint64_t));
    uint64_t *copy = calloc(n + 2, sizeof(uint64_t));
    if (!storage || !copy) return 2;
    storage[0] = storage[n + 1] = UINT64_C(0xd37a9c581234abcd);
    uint64_t *a = storage + 1;
    for (size_t i = 0; i < n; ++i) if (scanf("%" SCNu64, &a[i]) != 1) return 2;
    memcpy(copy, storage, (n + 2) * sizeof(uint64_t));
    uint64_t value = kernel(a, n, x);
    uint64_t elapsed = 0;
    unsigned long iterations = argc > 1 ? strtoul(argv[1], NULL, 10) : 0;
    if (iterations) {
        for (unsigned i = 0; i < 32; ++i) sink ^= kernel(a, n, x + i);
        uint64_t start = nanos();
        for (unsigned long i = 0; i < iterations; ++i) sink ^= kernel(a, n, x + i);
        elapsed = nanos() - start;
    }
    int mutated = memcmp(copy, storage, (n + 2) * sizeof(uint64_t)) != 0;
    printf("%" PRIu64 " %d %" PRIu64 "\n", value, mutated, elapsed);
    free(copy);
    free(storage);
    return 0;
}
