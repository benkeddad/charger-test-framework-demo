"""
Requirement traceability report: links requirements to test outcomes.

Reads:
- configs/requirements.yaml: requirement definitions (ID, text, priority)
- evidence/<latest>/results.json: test outcomes and their requirement IDs

Outputs:
- trace.md: requirement → test → outcome matrix
- Returns exit code:
  - 0: all requirements (especially 'must') have passing tests
  - 1: some 'must' requirement has no passing test (when --fail-on-uncovered)
  - 2: missing inputs or error
"""

import argparse
import io
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

# Fix Windows Unicode output issues by using UTF-8 wrapper
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def load_requirements(yaml_path: Path) -> Dict[str, Dict]:
    """Load requirements from YAML file.
    
    Returns dict: requirement_id -> {text, priority}
    """
    if not yaml_path.exists():
        print(f"ERROR: {yaml_path} not found", file=sys.stderr)
        return {}
    
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    if not data or "requirements" not in data:
        print(f"ERROR: {yaml_path} has no 'requirements' key", file=sys.stderr)
        return {}
    
    # Build dict: req_id -> {text, priority}
    requirements = {}
    for req in data["requirements"]:
        req_id = req.get("id")
        if req_id:
            requirements[req_id] = {
                "text": req.get("text", ""),
                "priority": req.get("priority", "should"),  # default to 'should'
            }
    
    return requirements


def find_latest_evidence() -> Optional[Path]:
    """Find the most recent evidence directory.
    
    Returns path to evidence/<UTC-timestamp>/ or None if not found.
    """
    evidence_dir = Path("evidence")
    if not evidence_dir.exists():
        return None
    
    # List all timestamped subdirectories, sorted lexicographically
    # (timestamp format is YYYY-MM-DDTHH-MM-SS.fff which sorts correctly)
    run_dirs = sorted([d for d in evidence_dir.iterdir() if d.is_dir()])
    
    if not run_dirs:
        return None
    
    # Return the most recent one
    return run_dirs[-1]


def load_test_results(results_file: Path) -> Dict[str, Dict]:
    """Load test results from results.json.
    
    Returns dict: (requirement_id -> {test_nodeid, outcome, ...})
    but keyed by requirement_id for easier lookup.
    """
    if not results_file.exists():
        print(f"ERROR: {results_file} not found", file=sys.stderr)
        return {}
    
    with open(results_file, encoding="utf-8") as f:
        results = json.load(f)
    
    if not isinstance(results, list):
        print(f"ERROR: {results_file} is not a list", file=sys.stderr)
        return {}
    
    # Build a mapping: requirement_id -> list of test results
    # (a requirement can be covered by multiple tests)
    req_to_tests: Dict[str, List[Dict]] = defaultdict(list)
    
    for result in results:
        nodeid = result.get("nodeid", "")
        outcome = result.get("outcome", "unknown")
        requirement_ids = result.get("requirement_ids", [])
        
        # If a test covers no requirements, still track it
        if not requirement_ids:
            requirement_ids = ["(uncovered)"]
        
        for req_id in requirement_ids:
            req_to_tests[req_id].append({
                "nodeid": nodeid,
                "outcome": outcome,
                "full_result": result,
            })
    
    return req_to_tests


def generate_trace_table(
    requirements: Dict[str, Dict],
    req_to_tests: Dict[str, List[Dict]],
) -> Tuple[str, bool]:
    """Generate markdown trace table.
    
    Returns:
    - markdown string for the trace table
    - bool: True if all 'must' requirements have at least one passing test
    """
    all_must_covered = True
    
    lines = []
    lines.append("# Requirement Traceability Matrix")
    lines.append("")
    lines.append("| ID | Requirement | Priority | Test Status |")
    lines.append("|---|---|---|---|")
    
    for req_id in sorted(requirements.keys()):
        req = requirements[req_id]
        text = req.get("text", "")
        priority = req.get("priority", "should")
        
        # Find tests that cover this requirement
        tests = req_to_tests.get(req_id, [])
        
        if not tests:
            # No tests for this requirement
            status = "❌ Not tested"
            if priority == "must":
                all_must_covered = False
        else:
            # Check if any test passed
            passed_tests = [t for t in tests if t["outcome"] == "passed"]
            failed_tests = [t for t in tests if t["outcome"] == "failed"]
            skipped_tests = [t for t in tests if t["outcome"] == "skipped"]
            
            if passed_tests:
                # At least one test passed
                status = f"✅ {len(passed_tests)} passed"
                if failed_tests:
                    status += f", {len(failed_tests)} failed"
                if skipped_tests:
                    status += f", {len(skipped_tests)} skipped"
            elif failed_tests:
                # Some tests failed, none passed
                status = f"❌ {len(failed_tests)} failed"
                if skipped_tests:
                    status += f", {len(skipped_tests)} skipped"
                if priority == "must":
                    all_must_covered = False
            elif skipped_tests:
                # Only skipped tests
                status = f"⚠️ {len(skipped_tests)} skipped"
                if priority == "must":
                    all_must_covered = False
            else:
                status = "❓ Unknown"
                if priority == "must":
                    all_must_covered = False
        
        # Truncate requirement text if too long
        display_text = text if len(text) <= 60 else text[:57] + "..."
        
        lines.append(f"| {req_id} | {display_text} | {priority} | {status} |")
    
    lines.append("")
    lines.append("Legend:")
    lines.append("- ✅ Requirement has at least one passing test")
    lines.append("- ❌ Requirement has no passing test (failed or not tested)")
    lines.append("- ⚠️ Requirement only has skipped tests")
    lines.append("")
    
    return "\n".join(lines), all_must_covered


def main():
    """Generate trace report and optionally fail on uncovered requirements."""
    parser = argparse.ArgumentParser(
        description="Generate requirement traceability matrix from test evidence.",
    )
    parser.add_argument(
        "--fail-on-uncovered",
        action="store_true",
        help="Exit 1 if any 'must' requirement has no passing test",
    )
    parser.add_argument(
        "--output", "-o",
        default="trace.md",
        help="Output file for trace matrix (default: trace.md)",
    )
    
    args = parser.parse_args()
    
    # Load requirements from YAML
    requirements_file = Path("configs/requirements.yaml")
    requirements = load_requirements(requirements_file)
    
    if not requirements:
        print("ERROR: No requirements loaded", file=sys.stderr)
        return 2
    
    # Find most recent evidence directory
    latest_evidence = find_latest_evidence()
    if not latest_evidence:
        print("ERROR: No evidence directory found. Run tests first.", file=sys.stderr)
        return 2
    
    # Load test results
    results_file = latest_evidence / "results.json"
    req_to_tests = load_test_results(results_file)
    
    # Generate trace table
    trace_md, all_must_covered = generate_trace_table(requirements, req_to_tests)
    
    # Write to file
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(trace_md)
    
    print(f"Trace report written to: {output_path}")
    print("")
    print(trace_md)
    
    # Check coverage if requested
    if args.fail_on_uncovered:
        if not all_must_covered:
            print("ERROR: Some 'must' requirements lack passing tests", file=sys.stderr)
            return 1
        else:
            print("✅ All 'must' requirements have passing tests")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
