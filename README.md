# MESI Snooping Cache Coherence Simulator

Python simulator for the MESI write-invalidate cache coherence protocol on a shared atomic bus. The project models private direct-mapped caches, main memory, and bus transactions for `BusRd`, `BusRdX`, `BusUpgr`, and `BusWB`.

This was developed for **EECE 422 - Project 1** by Tarek Bshinnati and Moataz Maarouf.

## Features

- Simulates MESI states: `Modified`, `Exclusive`, `Shared`, and `Invalid`
- Supports configurable numbers of cores, cache lines, and memory addresses
- Tracks read/write hits and misses, bus traffic, invalidations, writebacks, and silent upgrades
- Includes canonical workload traces for private, producer-consumer, and migratory sharing patterns
- Includes regression and edge-case tests for protocol transitions and invariants
- Compares full MESI behavior against an MSI-like configuration with the `E` state disabled

## Project Structure

| File | Description |
| --- | --- |
| `simulator.py` | Core simulator: MESI state machine, caches, bus, memory, stats, and system model |
| `traces.py` | Workload trace generators used by the experiments and tests |
| `experiments.py` | Runs the four project experiments and prints tabulated results |
| `test_simulator.py` | Regression and edge-case test suite |
| `requirements.txt` | Python dependency list |
| `required_libraries.py` | Small cross-platform dependency installer |
| `Project1_Report.docx` | Project report |
| `Project1_Handout.docx` | Project handout |

## Requirements

- Python 3.8 or newer
- `tabulate` for formatted experiment tables

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Or use the helper script:

```bash
python required_libraries.py
```

## Run Tests

```bash
python test_simulator.py
```

Expected result:

```text
Running 39 tests...
Passed: 140   Failed: 0
All tests passed.
```

## Run Experiments

```bash
python experiments.py
```

Save the experiment tables to a file:

```bash
python experiments.py > results.txt
```

## Default Configuration

```python
System(n=4, c=8, m=64, enable_e=True)
```

| Parameter | Meaning |
| --- | --- |
| `n` | Number of cores |
| `c` | Cache lines per core |
| `m` | Memory addresses |
| `enable_e` | Enables full MESI; set to `False` for an MSI-like comparison |

## Address Mapping

The cache is direct-mapped:

```text
index = address mod c
tag   = address // c
```

## Experiment Summary

- **Experiment 1:** Runs traces A, B, and C with `N=4`, `C=8`, `M=64`
- **Experiment 2:** Sweeps `N` over `2`, `4`, `6`, and `8` on Trace B
- **Experiment 3:** Sweeps `C` over `4`, `8`, `16`, and `32` on Trace C
- **Experiment 4:** Compares MESI with the `E` state disabled

## Modeling Notes

A write to a line already in `S` is counted as a write hit because the data is present in cache. The ownership cost is still counted through `BusUpgr` and invalidation counters.

The simulator counts events, not time. It does not model bus arbitration, pipelines, cache-to-cache transfer latency, set associativity, or false sharing.
