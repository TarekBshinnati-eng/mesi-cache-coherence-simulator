"""Small MESI snooping cache simulator."""

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum





class State(Enum):
    I = "I"
    S = "S"
    E = "E"
    M = "M"


@dataclass
class Line:
    tag: int = -1
    state: State = State.I

class Stats:
    def __init__(self, n):
        self.n = n
        self.r_hits = [0] * n
        self.r_misses = [0] * n
        self.w_hits = [0] * n
        self.w_misses = [0] * n
        self.inv_caused = [0] * n
        self.inv_received = [0] * n
        self.silent_upgr = [0] * n
        self.bus_rd = 0
        self.bus_rdx = 0
        self.bus_upgr = 0
        self.bus_wb = 0

    def total_hits(self):
        return sum(self.r_hits) + sum(self.w_hits)

    def total_misses(self):
        return sum(self.r_misses) + sum(self.w_misses)

    def total_accesses(self):
        return self.total_hits() + self.total_misses()

    def miss_rate(self):
        total = self.total_accesses()
        return 0.0 if total == 0 else self.total_misses() / total

    def total_bus(self):
        return self.bus_rd + self.bus_rdx + self.bus_upgr + self.bus_wb

    def total_inv(self):
        return sum(self.inv_caused)




class Cache:
    def __init__(self, cid, size):
        self.cid = cid
        self.size = size
        self.lines = [Line() for _ in range(size)]

    def slot(self, addr):
        return addr % self.size, addr // self.size

    def lookup(self, addr):
        idx, tag = self.slot(addr)
        line = self.lines[idx]
        hit = line.state != State.I and line.tag == tag
        return hit, line

    def snoop(self, addr):
        idx, tag = self.slot(addr)
        line = self.lines[idx]
        if line.tag == tag:
            return line.state
        return State.I

    def set_state(self, addr, state):
        idx, tag = self.slot(addr)
        line = self.lines[idx]
        if line.tag == tag:
            line.state = state

    def install(self, addr, state):
        idx, tag = self.slot(addr)
        self.lines[idx] = Line(tag, state)


class Memory:
    def __init__(self, size):
        self.size = size
        self.wb_count = 0

    def writeback(self, addr):
        self.wb_count += 1


class Bus:
    def __init__(self, caches, mem, stats):
        self.caches = caches
        self.mem = mem
        self.stats = stats

    def _others(self, cid):
        for cache in self.caches:
            if cache.cid != cid:
                yield cache

    def busrd(self, cid, addr):
        self.stats.bus_rd += 1
        shared = False
        for cache in self._others(cid):
            state = cache.snoop(addr)
            if state == State.M:
                self.mem.writeback(addr)
                self.stats.bus_wb += 1
                cache.set_state(addr, State.S)
                shared = True
            elif state == State.E:
                cache.set_state(addr, State.S)
                shared = True
            elif state == State.S:
                shared = True
        return shared

    def busrdx(self, cid, addr):
        self.stats.bus_rdx += 1
        caused = 0
        for cache in self._others(cid):
            state = cache.snoop(addr)
            if state == State.M:
                self.mem.writeback(addr)
                self.stats.bus_wb += 1
            if state in (State.M, State.E, State.S):
                cache.set_state(addr, State.I)
                self.stats.inv_received[cache.cid] += 1
                caused += 1
        self.stats.inv_caused[cid] += caused
        return caused

    def busupgr(self, cid, addr):
        self.stats.bus_upgr += 1
        caused = 0
        for cache in self._others(cid):
            if cache.snoop(addr) == State.S:
                cache.set_state(addr, State.I)
                self.stats.inv_received[cache.cid] += 1
                caused += 1
        self.stats.inv_caused[cid] += caused
        return caused

    def wb_evict(self, addr):
        self.mem.writeback(addr)
        self.stats.bus_wb += 1


class System:
    def __init__(self, n=4, c=8, m=64, enable_e=True):
        if n <= 0:
            raise ValueError("n must be positive")
        if c <= 0:
            raise ValueError("c must be positive")
        if m <= 0:
            raise ValueError("m must be positive")

        self.n = n
        self.c = c
        self.m = m
        self.enable_e = enable_e
        self.stats = Stats(n)
        self.memory = Memory(m)
        self.caches = [Cache(cid, c) for cid in range(n)]
        self.bus = Bus(self.caches, self.memory, self.stats)

    def _check_access(self, cid, op, addr):
        if op not in ("R", "W"):
            raise ValueError(f"unknown op {op}")
        if cid < 0 or cid >= self.n:
            raise ValueError(f"core {cid} out of range 0..{self.n - 1}")
        if addr < 0 or addr >= self.m:
            raise ValueError(f"addr {addr} outside memory range 0..{self.m - 1}")

    def _evict_if_needed(self, cache, addr):
        idx, tag = cache.slot(addr)
        line = cache.lines[idx]
        if line.state == State.I or line.tag == tag:
            return
        if line.state == State.M:
            old_addr = line.tag * cache.size + idx
            self.bus.wb_evict(old_addr)
        # Clean S/E lines can be dropped without a writeback.

    def access(self, cid, op, addr):
        self._check_access(cid, op, addr)
        cache = self.caches[cid]
        hit, line = cache.lookup(addr)

        if op == "R":
            if hit:
                self.stats.r_hits[cid] += 1
                return
            self.stats.r_misses[cid] += 1
            self._evict_if_needed(cache, addr)
            shared = self.bus.busrd(cid, addr)
            state = State.E if self.enable_e and not shared else State.S
            cache.install(addr, state)
            return

        if hit:
            self.stats.w_hits[cid] += 1
            if line.state == State.M:
                return
            if line.state == State.E:
                self.stats.silent_upgr[cid] += 1
                cache.set_state(addr, State.M)
                return
            if line.state == State.S:
                self.bus.busupgr(cid, addr)
                cache.set_state(addr, State.M)
                return

        self.stats.w_misses[cid] += 1
        self._evict_if_needed(cache, addr)
        self.bus.busrdx(cid, addr)
        cache.install(addr, State.M)

    def run(self, trace):
        for cid, op, addr in trace:
            self.access(cid, op, addr)
        return self.stats

    def invariant_check(self):
        by_addr = defaultdict(list)
        for cache in self.caches:
            for idx, line in enumerate(cache.lines):
                if line.state != State.I:
                    addr = line.tag * cache.size + idx
                    by_addr[addr].append((cache.cid, line.state))

        for addr, holders in by_addr.items():
            states = [state for _, state in holders]
            m_count = states.count(State.M)
            e_count = states.count(State.E)
            s_count = states.count(State.S)
            if m_count > 1:
                return False, f"addr {addr}: multiple M holders"
            if e_count > 1:
                return False, f"addr {addr}: multiple E holders"
            if m_count and (e_count or s_count):
                return False, f"addr {addr}: M coexists with E/S"
            if e_count and s_count:
                return False, f"addr {addr}: E coexists with S"
        return True, "ok"
