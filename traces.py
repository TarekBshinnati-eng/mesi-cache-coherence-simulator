"""Workload traces: each entry is (core_id, op, address)."""


def _positive(name, value):
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def trace_a_private(n=4, addrs_per_core=4, reps=3, m=64):
    """Private read trace: each core reads its own address block."""
    _positive("n", n)
    _positive("addrs_per_core", addrs_per_core)
    _positive("reps", reps)
    _positive("m", m)

    block = m // n
    if block == 0 or addrs_per_core > block:
        raise ValueError("Trace A needs a disjoint address window per core")

    trace = []
    for _ in range(reps):
        for cid in range(n):
            base = cid * block
            for off in range(addrs_per_core):
                trace.append((cid, "R", base + off))
    return trace


def trace_b_prodcons(n=4, n_addrs=6):
    """Producer-consumer trace: core 0 writes, then the others read."""
    _positive("n", n)
    _positive("n_addrs", n_addrs)

    trace = []
    for addr in range(n_addrs):
        trace.append((0, "W", addr))
    for cid in range(1, n):
        for addr in range(n_addrs):
            trace.append((cid, "R", addr))
    return trace


def trace_c_migratory(n=4, rounds=4, addr=0):
    """Migratory trace: one address moves from writer to writer."""
    _positive("n", n)
    _positive("rounds", rounds)
    if addr < 0:
        raise ValueError("addr must be non-negative")

    trace = []
    for _ in range(rounds):
        for cid in range(n):
            trace.append((cid, "W", addr))
    return trace


def trace_simple_rw():
    return [(0, "R", 0), (0, "W", 0), (0, "R", 0)]


def trace_two_cores_share():
    return [(0, "R", 5), (1, "R", 5), (0, "W", 5)]
