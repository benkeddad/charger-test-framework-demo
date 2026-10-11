#!/usr/bin/env python3
"""
Flake checker: Run full test suite N times to detect unreliable tests.

A test is flaky if it passes sometimes and fails other times. This tool runs the entire
pytest suite N times in separate subprocesses, collects results from each run's results.json,
and reports pass rates for every test. Any test with < 100% pass rate is flagged.

Usage:
    python tools/flake_check.py 20              # Run suite 20 times, show pass rates
    python tools/flake_check.py 20 --verbose    # Include individual run details

Exit codes:
    0 - All tests 100% reliable
    1 - One or more flaky tests detected
    2 - Error running tests
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# Enable UTF-8 output on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


def run_pytest_once(repo_root: Path) -> Optional[Path]:
    """
    Run pytest once, return path to the results.json from that run.

    Returns None if pytest failed or results.json was not created.
    """
    # Set environment to use src for module discovery
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    # Run pytest with minimal output, capturing to results.json via evidence plugin
    # Only run Phase 3 tests to avoid collection errors from Phase 1/2 tests needing pyvisa
    result = subprocess.run(
        ["pytest", "tests/test_phase_3_requirements.py", "-q", "--tb=short"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )

    # Find the most recent results.json in evidence/ directory
    evidence_dir = repo_root / "evidence"
    if not evidence_dir.exists():
        return None

    # results.json is in evidence/<UTC-timestamp>/results.json
    latest_results = None
    latest_time = 0
    for run_dir in sorted(evidence_dir.iterdir(), reverse=True):
        if run_dir.is_dir():
            results_file = run_dir / "results.json"
            if results_file.exists():
                return results_file

    return None


def load_results(results_file: Path) -> Optional[List[Dict]]:
    """Load and parse results.json, return list of test result dicts."""
    try:
        with open(results_file, encoding="utf-8") as f:
            data = json.load(f)
            # data is a list of test result objects
            if isinstance(data, list):
                return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: Failed to load {results_file}: {e}", file=sys.stderr)
    return None


def extract_test_name(nodeid: str) -> str:
    """Extract clean test name from pytest nodeid."""
    # nodeid format: tests/test_file.py::TestClass::test_method or tests/test_file.py::test_function
    # We want: test_file.py::test_method or test_file.py::TestClass::test_method
    parts = nodeid.split("::")
    if len(parts) >= 2:
        # Get file name (drop the path prefix)
        file_part = Path(parts[0]).name
        # Join with remaining parts (class/method names)
        return "::".join([file_part] + parts[1:])
    return nodeid


def run_flake_check(num_runs: int, verbose: bool = False) -> int:
    """
    Run pytest suite num_runs times, check for flaky tests.

    Returns 0 if all tests 100% reliable, 1 if flaky tests found, 2 on error.
    """
    repo_root = Path(__file__).parent.parent

    # Track pass/fail counts for each test across runs
    test_results: Dict[str, Dict[str, int]] = {}  # test_name -> {'passed': N, 'failed': N, 'skipped': N}
    all_test_names: set = set()

    print(f"Running pytest suite {num_runs} times to detect flaky tests...")
    print(f"Repo root: {repo_root}")
    print(f"PYTHONPATH=src for module discovery\n")

    # Run pytest num_runs times
    for run_num in range(1, num_runs + 1):
        print(f"  Run {run_num}/{num_runs}...", end=" ", flush=True)

        results_file = run_pytest_once(repo_root)
        if not results_file:
            print("[FAILED] (no results.json generated)")
            return 2

        results = load_results(results_file)
        if not results:
            print("[FAILED] (could not parse results.json)")
            return 2

        print(f"OK ({len(results)} tests)")

        # Tally results
        for test_record in results:
            nodeid = test_record.get("nodeid", "unknown")
            outcome = test_record.get("outcome", "unknown")  # passed, failed, skipped
            test_name = extract_test_name(nodeid)

            all_test_names.add(test_name)

            if test_name not in test_results:
                test_results[test_name] = {"passed": 0, "failed": 0, "skipped": 0}

            if outcome == "passed":
                test_results[test_name]["passed"] += 1
            elif outcome == "failed":
                test_results[test_name]["failed"] += 1
            elif outcome == "skipped":
                test_results[test_name]["skipped"] += 1

        if verbose:
            for test_record in results:
                nodeid = test_record.get("nodeid", "unknown")
                outcome = test_record.get("outcome", "unknown")
                test_name = extract_test_name(nodeid)
                symbol = "PASS" if outcome == "passed" else ("SKIP" if outcome == "skipped" else "FAIL")
                print(f"      [{symbol}] {test_name}: {outcome}")

    print("\n" + "=" * 100)
    print("FLAKE CHECK RESULTS")
    print("=" * 100 + "\n")

    # Report pass rates for every test
    flaky_tests = []
    all_pass_tests = []

    print(f"{'Test Name':<60} {'Pass Rate':<15} {'Passed':<8} {'Failed':<8} {'Skipped':<8}")
    print("-" * 100)

    for test_name in sorted(all_test_names):
        passed = test_results[test_name].get("passed", 0)
        failed = test_results[test_name].get("failed", 0)
        skipped = test_results[test_name].get("skipped", 0)
        total = passed + failed + skipped

        if total == 0:
            continue

        pass_rate = (passed / total) * 100 if total > 0 else 0
        rate_str = f"{pass_rate:.1f}% ({passed}/{total})"

        # Truncate test name if too long
        display_name = test_name if len(test_name) < 60 else test_name[:57] + "..."

        if pass_rate < 100:
            print(f"{display_name:<60} {rate_str:<15} {passed:<8} {failed:<8} {skipped:<8} [FLAKY]")
            flaky_tests.append((test_name, pass_rate, passed, failed, skipped))
        else:
            print(f"{display_name:<60} {rate_str:<15} {passed:<8} {failed:<8} {skipped:<8}")
            all_pass_tests.append(test_name)

    print("\n" + "=" * 100)
    print(f"Summary: {len(all_pass_tests)} reliable, {len(flaky_tests)} flaky")
    print("=" * 100)

    if flaky_tests:
        print("\nFlaky tests (< 100% pass rate):")
        for test_name, rate, passed, failed, skipped in sorted(flaky_tests, key=lambda x: x[1]):
            print(f"  [FAIL] {test_name}: {rate:.1f}% ({passed} passed, {failed} failed, {skipped} skipped)")
        return 1
    else:
        print("\n[SUCCESS] All tests are 100% reliable!")
        return 0


def main():
    """Parse CLI args and run flake check."""
    parser = argparse.ArgumentParser(
        description="Run pytest suite N times to detect flaky tests.",
        epilog="Exit 0 if all tests reliable, 1 if flaky tests found, 2 on error.",
    )
    parser.add_argument(
        "runs",
        type=int,
        help="Number of times to run the full test suite",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show individual test outcomes for each run",
    )

    args = parser.parse_args()

    if args.runs < 1:
        print("ERROR: runs must be >= 1", file=sys.stderr)
        sys.exit(2)  # Exit immediately with error code

    exit_code = run_flake_check(args.runs, verbose=args.verbose)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()


