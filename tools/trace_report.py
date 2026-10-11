"""
Tool to generate requirement traceability matrix and coverage report.

Reads:
- configs/requirements.yaml: requirement definitions (ID, text, priority)
- evidence/<latest>/results.json: test outcomes and requirement mappings

Outputs:
- trace.md: requirement → test → outcome matrix
- Exits with non-zero if --fail-on-uncovered and any 'must' requirement lacks a passing test
"""

# Placeholder for trace_report.py implementation (Phase 3)
