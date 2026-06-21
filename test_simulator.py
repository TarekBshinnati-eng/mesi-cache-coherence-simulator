"""
Extensive tests for the MESI simulator.
Covers every state transition, bus event, eviction case, and invariant.
"""

import sys as _sys
from simulator import System, State, Cache, Line
from traces import (
    trace_a_private, trace_b_prodcons, trace_c_migratory,
    trace_simple_rw, trace_two_cores_share,
)

_passed = 0
_failed = 0
_failures = []


def check(cond, msg):
    global _passed, _failed
    if cond:
        _passed += 1
    else:
        _failed += 1
        _failures.append(msg)
        print(f"  FAIL: {msg}")


def state_of(sys_, cid, addr):
    return sys_.caches[cid].snoop(addr)


#individual transition tests

def test_single_read_goes_to_E():
    """ PrRd on I with no other copies -> E (MESI silent-upgrade setup) """
    s = System(n=2, c=8, m=64)
    s.access(0, 'R', 5)
    check(state_of(s, 0, 5) == State.E, "single read should leave line in E")
    check(s.stats.r_misses[0] == 1, "read should count as miss")
    check(s.stats.bus_rd == 1, "one BusRd expected")
    check(s.stats.bus_wb == 0, "no writeback expected")


def test_read_with_other_copy_goes_to_S():
    """ PrRd on I when another cache has it -> S (not E) """
    s = System(n=2, c=8, m=64)
    s.access(0, 'R', 5)           # core 0: I->E
    s.access(1, 'R', 5)           # core 1: I->S, core 0: E->S
    check(state_of(s, 0, 5) == State.S, "core 0 should drop E->S")
    check(state_of(s, 1, 5) == State.S, "core 1 should be in S")
    check(s.stats.bus_rd == 2, "two BusRd")


def test_write_miss_to_M():
    """ PrWr on I -> M with BusRdX """
    s = System(n=2, c=8, m=64)
    s.access(0, 'W', 3)
    check(state_of(s, 0, 3) == State.M, "write miss should yield M")
    check(s.stats.bus_rdx == 1, "one BusRdX")
    check(s.stats.w_misses[0] == 1, "write miss counted")


def test_silent_upgrade_E_to_M():
    """ PrWr on E -> M silently, no bus traffic """
    s = System(n=2, c=8, m=64)
    s.access(0, 'R', 7)           # I->E
    before = s.stats.bus_rdx + s.stats.bus_upgr + s.stats.bus_rd + s.stats.bus_wb
    s.access(0, 'W', 7)           # E->M silent
    after = s.stats.bus_rdx + s.stats.bus_upgr + s.stats.bus_rd + s.stats.bus_wb
    check(state_of(s, 0, 7) == State.M, "E->M silent upgrade")
    check(before == after, "E->M must not issue any bus transaction")
    check(s.stats.silent_upgr[0] == 1, "silent upgrade counter bumped")


def test_write_hit_on_S_issues_BusUpgr():
    s = System(n=2, c=8, m=64)
    s.access(0, 'R', 2)
    s.access(1, 'R', 2)           # both in S now
    s.access(0, 'W', 2)           # S -> M via BusUpgr
    check(state_of(s, 0, 2) == State.M, "core 0 should be M")
    check(state_of(s, 1, 2) == State.I, "core 1 should be invalidated")
    check(s.stats.bus_upgr == 1, "one BusUpgr")
    check(s.stats.inv_caused[0] == 1, "core 0 caused 1 inv")
    check(s.stats.inv_received[1] == 1, "core 1 received 1 inv")


def test_busrd_on_M_triggers_writeback():
    """ snooped BusRd on M -> writeback + transition to S """
    s = System(n=2, c=8, m=64)
    s.access(0, 'W', 10)          # core 0: I->M
    check(state_of(s, 0, 10) == State.M, "core 0 should be M")
    s.access(1, 'R', 10)          # core 1 reads; core 0 writes back and drops to S
    check(state_of(s, 0, 10) == State.S, "core 0 should drop M->S")
    check(state_of(s, 1, 10) == State.S, "core 1 should get S (shared line)")
    check(s.stats.bus_wb == 1, "one writeback from snooped M")


def test_busrdx_on_M_triggers_writeback_and_invalidate():
    s = System(n=2, c=8, m=64)
    s.access(0, 'W', 10)          # core 0: M
    s.access(1, 'W', 10)          # core 1: BusRdX; core 0 writes back + invalidates
    check(state_of(s, 0, 10) == State.I, "core 0 invalidated")
    check(state_of(s, 1, 10) == State.M, "core 1 is M")
    check(s.stats.bus_wb == 1, "writeback on snooped M")
    check(s.stats.inv_received[0] == 1, "core 0 got invalidated once")

def test_eviction_of_M_line_writes_back():
    """ direct-mapped conflict evicting an M line must issue a BusWB """
    s = System(n=1, c=4, m=64)
    # addresses 0 and 4 both hit index 0 in a 4-line cache
    s.access(0, 'W', 0)           # core 0: addr 0 -> M at idx 0
    check(state_of(s, 0, 0) == State.M, "addr 0 should be M")
    s.access(0, 'R', 4)           # conflict evicts addr 0
    check(s.stats.bus_wb >= 1, "writeback on M eviction required")
    check(state_of(s, 0, 0) == State.I, "old addr no longer present (tag moved)")

def test_eviction_of_clean_line_is_silent():
    s = System(n=1, c=4, m=64)
    s.access(0, 'R', 0)           # idx 0, E state
    wb_before = s.stats.bus_wb
    s.access(0, 'R', 4)           # evict clean E line
    check(s.stats.bus_wb == wb_before, "no writeback for clean eviction")


def test_read_hit_no_bus_traffic():
    s = System(n=2, c=8, m=64)
    s.access(0, 'R', 1)
    bus_before = s.stats.total_bus()
    s.access(0, 'R', 1)
    check(s.stats.r_hits[0] == 1, "second read is a hit")
    check(s.stats.total_bus() == bus_before, "read hit must not add bus traffic")


def test_write_hit_on_M_no_bus_traffic():
    s = System(n=2, c=8, m=64)
    s.access(0, 'W', 9)           # I -> M
    bus_before = s.stats.total_bus()
    s.access(0, 'W', 9)           # stays M
    check(s.stats.w_hits[0] == 1, "second write is a hit")
    check(s.stats.total_bus() == bus_before, "M write must not add bus traffic")


def test_busrd_on_E_drops_to_S():
    s = System(n=2, c=8, m=64)
    s.access(0, 'R', 15)          # I -> E on core 0
    check(state_of(s, 0, 15) == State.E, "core 0 E")
    s.access(1, 'R', 15)          # core 1 reads; core 0 should drop to S
    check(state_of(s, 0, 15) == State.S, "E -> S on snooped BusRd")
    check(state_of(s, 1, 15) == State.S, "core 1 sees shared, goes to S")


def test_busrdx_on_E_invalidates_no_wb():
    """ BusRdX snooped while in E -> invalidate, no writeback (E is clean) """
    s = System(n=2, c=8, m=64)
    s.access(0, 'R', 20)          # I -> E
    wb_before = s.stats.bus_wb
    s.access(1, 'W', 20)          # core 1 writes; core 0 invalidates silently
    check(state_of(s, 0, 20) == State.I, "E invalidated")
    check(state_of(s, 1, 20) == State.M, "core 1 M")
    check(s.stats.bus_wb == wb_before, "E invalidation should not writeback")



def test_invariant_after_random_ish_trace():
    """ after running the canonical traces, invariants should hold """
    for tgen, name in [
        (trace_a_private(), 'A'),
        (trace_b_prodcons(), 'B'),
        (trace_c_migratory(), 'C'),
    ]:
        s = System()
        s.run(tgen)
        ok, msg = s.invariant_check()
        check(ok, f"invariant on trace {name}: {msg}")


def test_trace_a_expectations():
    """ trace A: cold misses only on first pass, no invalidations """
    s = System(n=4, c=8, m=64)
    t = trace_a_private(n=4, addrs_per_core=4, reps=3, m=64)
    s.run(t)
    # each core reads 4 disjoint addresses, no sharing -> 4 misses per core, rest hits
    for i in range(4):
        check(s.stats.r_misses[i] == 4, f"core {i} should have 4 cold misses")
    check(sum(s.stats.inv_caused) == 0, "no invalidations on trace A")
    check(s.stats.bus_rdx == 0, "no BusRdX on read-only trace")
    check(s.stats.bus_upgr == 0, "no BusUpgr on read-only trace")


def test_trace_b_expectations():
    """ trace B: core 0 writes then others read; should see writebacks, sharing """
    s = System(n=4, c=8, m=64)
    t = trace_b_prodcons(n=4, n_addrs=6)
    s.run(t)
    check(s.stats.w_misses[0] == 6, "core 0 should have 6 write misses")
    check(s.stats.bus_rdx == 6, "6 BusRdX from core 0 writes")
    # Each of the 6 addrs: core 1 reads (M->S + WB), core 2 reads (S->S), core 3 reads (S->S).
    # So exactly 6 writebacks (one per line from M->S via first snooped BusRd).
    check(s.stats.bus_wb == 6, "one writeback per produced address")
    # core 1..3 each read 6 addrs as misses
    for cid in [1, 2, 3]:
        check(s.stats.r_misses[cid] == 6, f"core {cid} read 6 misses")


def test_trace_c_expectations():
    """ trace C: rounds=4, n=4 => 16 writes, all on same addr.
        First write is I->M miss (no inv). Next 15 writes are M of another core -> BusRdX with wb+inv. """
    s = System(n=4, c=8, m=64)
    t = trace_c_migratory(n=4, rounds=4, addr=0)
    s.run(t)
    total_writes = 4 * 4
    check(sum(s.stats.w_misses) == total_writes, "all writes are misses (ownership bouncing)")
    # invalidations: first write doesn't invalidate anyone; the next 15 each invalidate exactly 1.
    check(sum(s.stats.inv_caused) == total_writes - 1,
          f"expected {total_writes-1} invalidations, got {sum(s.stats.inv_caused)}")
    check(s.stats.bus_rdx == total_writes,
          f"{total_writes} BusRdX transactions expected")
    # writebacks: after the first write (M on core 0), every subsequent BusRdX triggers a writeback
    check(s.stats.bus_wb == total_writes - 1,
          f"{total_writes-1} writebacks expected")


def test_same_core_same_address_repeats():
    """ edge: same core writes same addr repeatedly -> first write only, rest silent """
    s = System(n=2, c=8, m=64)
    for _ in range(5):
        s.access(0, 'W', 11)
    check(s.stats.w_misses[0] == 1, "only first W is a miss")
    check(s.stats.w_hits[0] == 4, "others are hits")
    check(s.stats.bus_rdx == 1, "only one BusRdX")


def test_read_after_invalidation_is_miss():
    s = System(n=2, c=8, m=64)
    s.access(0, 'R', 6)           # core 0: E
    s.access(1, 'W', 6)           # core 1: BusRdX, core 0 -> I
    check(state_of(s, 0, 6) == State.I, "core 0 invalidated")
    s.access(0, 'R', 6)           # should miss
    check(s.stats.r_misses[0] == 2, "second read after invalidation is also a miss")


def test_multiple_sharers_all_invalidated_on_write():
    s = System(n=4, c=8, m=64)
    for cid in range(4):
        s.access(cid, 'R', 30)   # all end up in S
    # now core 0 writes
    s.access(0, 'W', 30)
    check(state_of(s, 0, 30) == State.M, "core 0 in M")
    for cid in [1, 2, 3]:
        check(state_of(s, cid, 30) == State.I, f"core {cid} invalidated")
    check(s.stats.inv_caused[0] == 3, "core 0 caused 3 invalidations")
    check(s.stats.bus_upgr == 1, "one BusUpgr for S->M")


def test_disable_E_behaves_like_MSI():
    """ with enable_e=False, solo read miss must go to S, and subsequent write needs BusUpgr """
    s = System(n=2, c=8, m=64, enable_e=False)
    s.access(0, 'R', 50)
    check(state_of(s, 0, 50) == State.S, "no E state allowed")
    bus_before = s.stats.total_bus()
    s.access(0, 'W', 50)
    check(state_of(s, 0, 50) == State.M, "S->M after write")
    check(s.stats.bus_upgr == 1, "BusUpgr required even though nobody else has it")
    check(s.stats.total_bus() > bus_before, "disabled E means this is not silent")


def test_address_at_memory_boundary():
    s = System(n=2, c=8, m=64)
    s.access(0, 'R', 63)           # highest legal addr
    check(s.stats.r_misses[0] == 1, "boundary read works")
    s.access(0, 'R', 0)            # lowest addr
    check(s.stats.r_misses[0] == 2, "zero address works")


def test_invalid_address_raises():
    s = System(n=2, c=8, m=64)
    raised = False
    try:
        s.access(0, 'R', 64)
    except ValueError:
        raised = True
    check(raised, "out-of-range addr should raise")


def test_invalid_core_raises():
    s = System(n=2, c=8, m=64)
    raised = False
    try:
        s.access(5, 'R', 0)
    except ValueError:
        raised = True
    check(raised, "out-of-range core should raise")


def test_invalid_op_raises():
    s = System(n=2, c=8, m=64)
    raised = False
    try:
        s.access(0, 'X', 0)
    except ValueError:
        raised = True
    check(raised, "unknown op should raise")


def test_tag_conflict_but_same_index_different_addr():
    """ direct-mapped: addrs 0 and 8 conflict at idx 0 when C=8 """
    s = System(n=1, c=8, m=64)
    s.access(0, 'R', 0)
    s.access(0, 'R', 8)           # conflicts, evicts addr 0
    check(state_of(s, 0, 0) == State.I, "evicted addr is gone")
    check(state_of(s, 0, 8) == State.E, "new addr installed in E")


def test_invariant_caused_equals_received_globally():
    """ sanity: total inv_caused across cores equals total inv_received across cores """
    for tgen in [trace_a_private(), trace_b_prodcons(), trace_c_migratory()]:
        s = System()
        s.run(tgen)
        check(sum(s.stats.inv_caused) == sum(s.stats.inv_received),
              f"inv caused ({sum(s.stats.inv_caused)}) != received "
              f"({sum(s.stats.inv_received)})")


def test_empty_trace():
    s = System()
    s.run([])
    check(s.stats.total_accesses() == 0, "empty trace: no accesses")
    check(s.stats.total_bus() == 0, "empty trace: no bus traffic")
    ok, _ = s.invariant_check()
    check(ok, "empty system is invariant-ok")


def test_single_core_no_coherence_traffic():
    s = System(n=1, c=8, m=64)
    s.run([(0, 'R', i) for i in range(8)])
    check(s.stats.bus_rdx == 0, "single-core reads: no BusRdX")
    check(s.stats.bus_upgr == 0, "single-core reads: no BusUpgr")
    check(sum(s.stats.inv_caused) == 0, "no invalidations possible with 1 core")


def test_write_then_read_same_core():
    """ same core: write (I->M) then read should hit, stay M """
    s = System(n=2, c=8, m=64)
    s.access(0, 'W', 12)
    bus_before = s.stats.total_bus()
    s.access(0, 'R', 12)
    check(s.stats.r_hits[0] == 1, "read after write is a hit")
    check(state_of(s, 0, 12) == State.M, "state stays M")
    check(s.stats.total_bus() == bus_before, "no bus traffic on M read hit")


def test_read_then_different_core_write():
    """ core A reads (E), core B writes -> A invalidated (no writeback because clean) """
    s = System(n=2, c=8, m=64)
    s.access(0, 'R', 25)          # I->E
    wb_before = s.stats.bus_wb
    s.access(1, 'W', 25)          # BusRdX; core 0 invalidates E->I silently
    check(state_of(s, 0, 25) == State.I, "A invalidated")
    check(state_of(s, 1, 25) == State.M, "B is M")
    check(s.stats.bus_wb == wb_before, "no writeback (E was clean)")


def test_direct_mapped_conflict_after_M_triggers_writeback_once():
    s = System(n=1, c=2, m=32)    # very small cache to force conflicts
    s.access(0, 'W', 0)           # M at idx 0
    s.access(0, 'W', 2)           # conflict at idx 0, evict M
    check(s.stats.bus_wb == 1, "exactly one writeback")


def test_bus_counts_consistent_across_experiments():
    """ running experiments back-to-back shouldn't share state """
    t = trace_c_migratory(n=4, rounds=2, addr=0)
    s1 = System()
    s1.run(t)
    s2 = System()
    s2.run(t)
    check(s1.stats.total_bus() == s2.stats.total_bus(),
          "stateless: same trace -> same bus count")


def test_dense_write_hammer():
    """ stress: many cores hammering many addresses, protocol still consistent """
    s = System(n=4, c=8, m=64)
    trace = []
    for a in range(0, 16, 2):
        for cid in range(4):
            trace.append((cid, 'W', a))
            trace.append((cid, 'R', a))
    s.run(trace)
    ok, msg = s.invariant_check()
    check(ok, f"stress test invariant: {msg}")
    check(sum(s.stats.inv_caused) == sum(s.stats.inv_received),
          "caused == received under stress")


def test_E_state_does_not_appear_when_disabled():
    s = System(n=4, c=8, m=64, enable_e=False)
    s.run(trace_a_private(n=4))
    for c in s.caches:
        for ln in c.lines:
            check(ln.state != State.E, "no E state when disabled")


def test_busupgr_on_E_or_M_holder_is_impossible():
    """ if we're in S issuing a BusUpgr, nobody else can be in E or M.
        this is an invariant check, not a direct test, but we verify it
        indirectly by checking MESI rules after all canonical traces. """
    # covered by test_invariant_after_random_ish_trace and MESI protocol correctness
    pass


def test_read_after_evicted_line_is_cold_miss_again():
    s = System(n=1, c=2, m=32)
    s.access(0, 'R', 0)           # idx 0
    s.access(0, 'R', 2)           # evict idx 0
    s.access(0, 'R', 0)           # cold again
    check(s.stats.r_misses[0] == 3, "each fresh install is a miss")


def test_writeback_count_matches_m_evictions_and_m_snoops():
    """ every BusWB corresponds to exactly one of: M eviction, M snooped on BusRd, or M snooped on BusRdX """
    # crude but: on trace C, first write: 1 miss on I (no wb).
    # each subsequent write: BusRdX hits a remote M (wb) and that core invalidates.
    # so wb count == writes - 1
    s = System(n=4, c=8, m=64)
    s.run(trace_c_migratory(n=4, rounds=5, addr=0))
    total_writes = 4 * 5
    check(s.stats.bus_wb == total_writes - 1, "writebacks match M transitions")


def test_bad_system_config_raises():
    #edge case: bad simulator sizes should fail early with a clear error"""
    for kwargs in [{'n': 0}, {'c': 0}, {'m': 0}]:
        raised = False
        try:
            System(**kwargs)
        except ValueError:
            raised = True
        check(raised, f"bad config should raise: {kwargs}")


def test_trace_a_rejects_overlapping_private_windows():
    #edge case: Trace A should stay private when custom sizes are used
    raised = False
    try:
        trace_a_private(n=4, addrs_per_core=20, reps=1, m=64)
    except ValueError:
        raised = True
    check(raised, "Trace A should reject overlapping core address ranges")

    t = trace_a_private(n=4, addrs_per_core=16, reps=1, m=64)
    addrs_by_core = {cid: set() for cid in range(4)}
    for cid, _, addr in t:
        addrs_by_core[cid].add(addr)
    overlap = set()
    for cid in range(4):
        for other in range(cid + 1, 4):
            overlap |= addrs_by_core[cid] & addrs_by_core[other]
    check(not overlap, "Trace A address windows remain disjoint at the boundary")


# ---- registry + runner ----
TESTS = [
    test_single_read_goes_to_E,
    test_read_with_other_copy_goes_to_S,
    test_write_miss_to_M,
    test_silent_upgrade_E_to_M,
    test_write_hit_on_S_issues_BusUpgr,
    test_busrd_on_M_triggers_writeback,
    test_busrdx_on_M_triggers_writeback_and_invalidate,
    test_eviction_of_M_line_writes_back,
    test_eviction_of_clean_line_is_silent,
    test_read_hit_no_bus_traffic,
    test_write_hit_on_M_no_bus_traffic,
    test_busrd_on_E_drops_to_S,
    test_busrdx_on_E_invalidates_no_wb,
    test_invariant_after_random_ish_trace,
    test_trace_a_expectations,
    test_trace_b_expectations,
    test_trace_c_expectations,
    test_same_core_same_address_repeats,
    test_read_after_invalidation_is_miss,
    test_multiple_sharers_all_invalidated_on_write,
    test_disable_E_behaves_like_MSI,
    test_address_at_memory_boundary,
    test_invalid_address_raises,
    test_invalid_core_raises,
    test_invalid_op_raises,
    test_tag_conflict_but_same_index_different_addr,
    test_invariant_caused_equals_received_globally,
    test_empty_trace,
    test_single_core_no_coherence_traffic,
    test_write_then_read_same_core,
    test_read_then_different_core_write,
    test_direct_mapped_conflict_after_M_triggers_writeback_once,
    test_bus_counts_consistent_across_experiments,
    test_dense_write_hammer,
    test_E_state_does_not_appear_when_disabled,
    test_read_after_evicted_line_is_cold_miss_again,
    test_writeback_count_matches_m_evictions_and_m_snoops,
    test_bad_system_config_raises,
    test_trace_a_rejects_overlapping_private_windows,
]


def main():
    global _passed, _failed, _failures
    print(f"Running {len(TESTS)} tests...\n")
    for t in TESTS:
        name = t.__name__
        print(f"  {name}")
        try:
            t()
        except Exception as e:
            _failed += 1
            _failures.append(f"{name}: raised {type(e).__name__}: {e}")
            print(f"    EXCEPTION: {e}")

    print(f"\n{'=' * 60}")
    print(f"Passed: {_passed}   Failed: {_failed}")
    if _failures:
        print("\nFailures:")
        for f in _failures:
            print(f"  - {f}")
        _sys.exit(1)
    else:
        print("All tests passed.")


if __name__ == '__main__':
    main()
