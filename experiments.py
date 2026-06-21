"""Runs the project experiments."""

from tabulate import tabulate

from simulator import System
from traces import trace_a_private, trace_b_prodcons, trace_c_migratory


HEADERS = [
    "R hits", "R misses", "W hits", "W misses", "miss rate",
    "BusRd", "BusRdX", "BusUpgr", "BusWB", "Total bus",
    "Invalidations", "Silent upgr",
]


def run_one(trace, n=4, c=8, m=64, enable_e=True):
    sim = System(n=n, c=c, m=m, enable_e=enable_e)
    sim.run(trace)
    ok, msg = sim.invariant_check()
    if not ok:
        raise RuntimeError(f"invariant broken: {msg}")
    return sim.stats


def global_row(name, stats):
    return [
        name,
        sum(stats.r_hits),
        sum(stats.r_misses),
        sum(stats.w_hits),
        sum(stats.w_misses),
        f"{stats.miss_rate():.3f}",
        stats.bus_rd,
        stats.bus_rdx,
        stats.bus_upgr,
        stats.bus_wb,
        stats.total_bus(),
        stats.total_inv(),
        sum(stats.silent_upgr),
    ]


def exp1():
    print("\n" + "=" * 70)
    print("EXPERIMENT 1 - Baseline behavior (N=4, C=8, M=64)")
    print("=" * 70)

    traces = {
        "A (private)": trace_a_private(n=4, addrs_per_core=4, reps=3, m=64),
        "B (prod/cons)": trace_b_prodcons(n=4, n_addrs=6),
        "C (migratory)": trace_c_migratory(n=4, rounds=4, addr=0),
    }

    rows = []
    per_core = []
    for name, trace in traces.items():
        stats = run_one(trace)
        rows.append(global_row(name, stats))
        for cid in range(stats.n):
            per_core.append([
                name[0], cid, stats.r_hits[cid], stats.r_misses[cid],
                stats.w_hits[cid], stats.w_misses[cid],
                stats.inv_caused[cid], stats.inv_received[cid],
            ])

    print(tabulate(rows, headers=["Trace"] + HEADERS, tablefmt="grid"))
    print("\nPer-core details for Experiment 1:")
    print(tabulate(
        per_core,
        headers=["Trace", "Core", "R hits", "R miss", "W hits", "W miss", "Inv caused", "Inv recv"],
        tablefmt="grid",
    ))


def exp2():
    print("\n" + "=" * 70)
    print("EXPERIMENT 2 - Scaling N on Trace B (C=8, M=64)")
    print("=" * 70)

    rows = []
    for n in [2, 4, 6, 8]:
        stats = run_one(trace_b_prodcons(n=n, n_addrs=6), n=n)
        rows.append([n, stats.bus_rd, stats.bus_rdx, stats.bus_upgr,
                     stats.bus_wb, stats.total_bus(), stats.total_inv()])
    print(tabulate(rows, headers=["N", "BusRd", "BusRdX", "BusUpgr", "BusWB", "Total bus", "Inv"], tablefmt="grid"))


def exp3():
    print("\n" + "=" * 70)
    print("EXPERIMENT 3 - Scaling C on Trace C (N=4, M=64)")
    print("=" * 70)

    rows = []
    for c in [4, 8, 16, 32]:
        stats = run_one(trace_c_migratory(n=4, rounds=4, addr=0), c=c)
        rows.append([c, f"{stats.miss_rate():.3f}", stats.total_bus(),
                     stats.bus_rd, stats.bus_rdx, stats.bus_upgr, stats.bus_wb])
    print(tabulate(rows, headers=["C", "miss rate", "Total bus", "BusRd", "BusRdX", "BusUpgr", "BusWB"], tablefmt="grid"))

    print("\nSupplementary capacity-sensitive private workload:")
    extra = []
    for c in [4, 8, 16, 32]:
        trace = []
        for _ in range(3):
            for cid in range(4):
                for off in range(16):
                    trace.append((cid, "R", cid * 16 + off))
        stats = run_one(trace, c=c)
        extra.append([c, f"{stats.miss_rate():.3f}", stats.total_bus(), stats.bus_rd, stats.bus_wb])
    print(tabulate(extra, headers=["C", "miss rate", "Total bus", "BusRd", "BusWB"], tablefmt="grid"))


def exp4():
    print("\n" + "=" * 70)
    print("EXPERIMENT 4 - Silent upgrades (N=4, C=8, M=64)")
    print("=" * 70)

    trace = trace_a_private(n=4, addrs_per_core=4, reps=3, m=64)
    rows = []
    for label, enable_e in [("MESI (E enabled)", True), ("E disabled", False)]:
        stats = run_one(trace, enable_e=enable_e)
        rows.append([label, stats.bus_rd, stats.bus_rdx, stats.bus_upgr,
                     stats.bus_wb, stats.total_bus(), sum(stats.silent_upgr)])
    print(tabulate(rows, headers=["Config", "BusRd", "BusRdX", "BusUpgr", "BusWB", "Total bus", "Silent upgr"], tablefmt="grid"))

    print("\nRead-then-write private workload:")
    trace2 = []
    block = 64 // 4
    for rep in range(3):
        op = "R" if rep == 0 else "W"
        for cid in range(4):
            for off in range(4):
                trace2.append((cid, op, cid * block + off))

    rows = []
    for label, enable_e in [("MESI (E enabled)", True), ("E disabled", False)]:
        stats = run_one(trace2, enable_e=enable_e)
        rows.append([label, stats.bus_rd, stats.bus_rdx, stats.bus_upgr,
                     stats.bus_wb, stats.total_bus(), sum(stats.silent_upgr)])
    print(tabulate(rows, headers=["Config", "BusRd", "BusRdX", "BusUpgr", "BusWB", "Total bus", "Silent upgr"], tablefmt="grid"))


if __name__ == "__main__":
    exp1()
    exp2()
    exp3()
    exp4()
