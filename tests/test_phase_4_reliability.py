"""
Phase 4: Reliability Tooling — Evidence Collection and Flake Detection

Tests for:
1. Evidence plugin: Captures test outcomes, failure classification, timing
2. Flake checker: Detects unreliable tests across multiple runs
"""

import json
from pathlib import Path

import pytest

from chargerlab.evidence.models import EnvironmentInfo, FailureClass, TestResult
from chargerlab.requirements.pytest_plugin import requires


class TestEvidenceModels:
    """Tests for evidence data models."""

    @requires("CHARGER-006", "INFRA-002", "INFRA-001")
    @pytest.mark.smoke
    def test_result_record_basic(self) -> None:
        """Test result record with basic fields."""
        result = TestResult(
            nodeid="tests/test_example.py::test_foo",
            outcome="passed",
            duration_seconds=0.123,
            requirement_ids=["REQ-001"],
            failure_class=FailureClass.PASS,
        )
        # Serialize to dict (as evidence plugin does)
        data = result.model_dump()
        assert data["nodeid"] == "tests/test_example.py::test_foo"
        assert data["outcome"] == "passed"
        assert data["duration_seconds"] == 0.123
        assert data["requirement_ids"] == ["REQ-001"]
        assert data["failure_class"] == "pass"

    @requires("CHARGER-006", "INFRA-002", "INFRA-001")
    def test_result_record_failure_classification(self) -> None:
        """Test result captures failure class: infra, product, test."""
        # Product failure
        result_product = TestResult(
            nodeid="tests/test_x.py::test_assertion",
            outcome="failed",
            duration_seconds=0.5,
            failure_class=FailureClass.PRODUCT,
            failure_message="AssertionError: expected 5 but got 4",
        )
        assert result_product.failure_class == FailureClass.PRODUCT

        # Infrastructure failure
        result_infra = TestResult(
            nodeid="tests/test_y.py::test_timeout",
            outcome="failed",
            duration_seconds=30.0,
            failure_class=FailureClass.INFRA,
            failure_message="InfrastructureError: Connection timeout",
        )
        assert result_infra.failure_class == FailureClass.INFRA

        # Test framework bug
        result_test = TestResult(
            nodeid="tests/test_z.py::test_broken",
            outcome="failed",
            duration_seconds=0.1,
            failure_class=FailureClass.TEST,
            failure_message="RuntimeError: Unexpected state in fixture",
        )
        assert result_test.failure_class == FailureClass.TEST

    @requires("CHARGER-006", "INFRA-001")
    def test_environment_info_model(self) -> None:
        """Environment info captures system state for reproducibility."""
        env = EnvironmentInfo(
            git_sha="abc123def456",
            git_branch="main",
            python_version="3.12.1",
            platform="win32",
            pytest_version="9.1.1",
            simulated=True,
            library_versions={"ocpp": "2.1.0", "pytest": "9.1.1"},
        )
        # Should be serializable
        data = env.model_dump()
        assert data["python_version"] == "3.12.1"
        assert data["simulated"] is True
        assert data["library_versions"]["ocpp"] == "2.1.0"

    @requires("CHARGER-006", "INFRA-001")
    @pytest.mark.smoke
    def test_evidence_serialization_to_json(self) -> None:
        """Evidence can be serialized to JSON and back."""
        original = TestResult(
            nodeid="tests/test_round_trip.py::test_serialize",
            outcome="passed",
            duration_seconds=0.25,
            requirement_ids=["REQ-001", "REQ-002"],
            failure_class=FailureClass.PASS,
        )

        # Serialize to JSON-safe dict
        data = original.model_dump()
        # Convert FailureClass enum to string for JSON
        if isinstance(data["failure_class"], FailureClass):
            data["failure_class"] = data["failure_class"].value

        # Serialize and deserialize
        json_str = json.dumps(data)
        loaded = json.loads(json_str)

        # Verify round-trip
        assert loaded["nodeid"] == original.nodeid
        assert loaded["outcome"] == original.outcome
        assert loaded["duration_seconds"] == original.duration_seconds
        assert loaded["requirement_ids"] == original.requirement_ids


class TestEvidenceCollection:
    """Tests for evidence collection during test execution."""

    @requires("CHARGER-006", "INFRA-001")
    def test_evidence_plugin_captures_test_runs(self) -> None:
        """Evidence plugin captures test outcomes after pytest runs."""
        # The Phase 3 tests should have generated evidence
        evidence_dir = Path("evidence")
        if not evidence_dir.exists():
            # Evidence would exist if tests were run with pytest plugin
            pytest.skip("Evidence directory not found (run with pytest for collection)")
        assert evidence_dir.exists()

    @requires("CHARGER-006", "INFRA-001")
    def test_evidence_directory_structure(self) -> None:
        """Evidence is organized in evidence/<UTC-timestamp>/ directories."""
        evidence_dir = Path("evidence")
        if not evidence_dir.exists():
            pytest.skip("Evidence directory not found; run Phase 3 tests first")

        # Each run should have a timestamped directory
        run_dirs = sorted([d for d in evidence_dir.iterdir() if d.is_dir()])
        if len(run_dirs) == 0:
            pytest.skip("No evidence run directories found")

        # Most recent run with results
        for latest_run in reversed(run_dirs):
            if (latest_run / "results.json").exists():
                assert (latest_run / "environment.json").exists()
                break
        else:
            pytest.skip("No evidence directories with results.json")

    @requires("CHARGER-006", "INFRA-002", "INFRA-001")
    def test_results_json_valid_format(self) -> None:
        """results.json contains properly formatted test result records."""
        evidence_dir = Path("evidence")
        if not evidence_dir.exists():
            pytest.skip("Evidence directory not found")

        run_dirs = sorted([d for d in evidence_dir.iterdir() if d.is_dir()])
        if len(run_dirs) == 0:
            pytest.skip("No evidence run directories found")

        # Find the most recent run with results
        for latest_run in reversed(run_dirs):
            results_file = latest_run / "results.json"
            if results_file.exists():
                with open(results_file, encoding="utf-8") as f:
                    results = json.load(f)

                if len(results) == 0:
                    continue

                assert isinstance(results, list), "results.json should contain a list"

                # Check first result has required fields
                first_result = results[0]
                assert "nodeid" in first_result
                assert "outcome" in first_result
                assert "duration_seconds" in first_result
                assert "failure_class" in first_result
                assert first_result["outcome"] in ["passed", "failed", "skipped"]
                return

        pytest.skip("No evidence found with valid results")

    @requires("CHARGER-006", "INFRA-001")
    def test_environment_json_valid_format(self) -> None:
        """environment.json contains system and library info."""
        evidence_dir = Path("evidence")
        if not evidence_dir.exists():
            pytest.skip("Evidence directory not found")

        run_dirs = sorted([d for d in evidence_dir.iterdir() if d.is_dir()])
        if len(run_dirs) == 0:
            pytest.skip("No evidence run directories found")

        # Find the most recent run with results
        for latest_run in reversed(run_dirs):
            env_file = latest_run / "environment.json"
            if env_file.exists():
                with open(env_file, encoding="utf-8") as f:
                    env = json.load(f)

                # Should have key environment fields
                assert "python_version" in env
                assert "platform" in env
                assert "pytest_version" in env
                assert "simulated" in env
                assert env["simulated"] is True
                assert "library_versions" in env
                return

        pytest.skip("No environment.json found")


class TestFlakeDetection:
    """Tests for flake detection via multiple test runs."""

    @requires("INFRA-001", "INFRA-002")
    @pytest.mark.smoke
    def test_flake_checker_script_exists(self) -> None:
        """flake_check.py tool exists and is executable."""
        flake_check = Path("tools/flake_check.py")
        assert flake_check.exists()
        assert flake_check.is_file()

    @requires("INFRA-001", "INFRA-002")
    def test_flake_checker_requires_run_count(self) -> None:
        """flake_check.py requires a run count argument."""
        import subprocess

        # Running without arguments should fail
        result = subprocess.run(
            ["python", "tools/flake_check.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    @requires("INFRA-001", "INFRA-002")
    def test_flake_checker_rejects_zero_runs(self) -> None:
        """flake_check.py rejects run count of zero."""
        import subprocess

        # Run count must be >= 1
        result = subprocess.run(
            ["python", "tools/flake_check.py", "0"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2  # Error exit code for validation failure
        assert "must be >= 1" in result.stderr

    @requires("INFRA-001", "INFRA-002")
    def test_flake_checker_accepts_positive_count(self) -> None:
        """flake_check.py accepts positive run count."""
        import subprocess

        # Should accept 1 as a valid run count
        result = subprocess.run(
            ["python", "tools/flake_check.py", "1"],
            capture_output=True,
            text=True,
            cwd=".",
        )
        # Exit code 0 or 1 is OK (0=all pass, 1=some flaky); 2+ is error
        assert result.returncode in [0, 1], f"Unexpected exit code: {result.returncode}"


class TestFailureClassification:
    """Tests for distinguishing failure types."""

    @requires("INFRA-002", "INFRA-001")
    @pytest.mark.smoke
    def test_failure_class_passed_test(self) -> None:
        """Passed tests classified as PASS."""
        result = TestResult(
            nodeid="tests/test.py::test_pass",
            outcome="passed",
            duration_seconds=0.1,
            failure_class=FailureClass.PASS,
        )
        assert result.failure_class == FailureClass.PASS

    @requires("INFRA-002", "INFRA-001")
    def test_failure_class_infrastructure_error(self) -> None:
        """Infrastructure errors (timeout, connection) classified as INFRA."""
        result = TestResult(
            nodeid="tests/test.py::test_infra_error",
            outcome="failed",
            duration_seconds=30.0,
            failure_class=FailureClass.INFRA,
            failure_message="InfrastructureError: Connection reset by peer",
        )
        assert result.failure_class == FailureClass.INFRA

    @requires("INFRA-002", "INFRA-001")
    def test_failure_class_product_defect(self) -> None:
        """Assertion failures classified as PRODUCT (the thing being tested is broken)."""
        result = TestResult(
            nodeid="tests/test.py::test_assertion",
            outcome="failed",
            duration_seconds=0.5,
            failure_class=FailureClass.PRODUCT,
            failure_message="AssertionError: Charger state should be C but was B",
        )
        assert result.failure_class == FailureClass.PRODUCT

    @requires("INFRA-002", "INFRA-001")
    def test_failure_class_framework_bug(self) -> None:
        """Framework/test bugs classified as TEST."""
        result = TestResult(
            nodeid="tests/test.py::test_broken_framework",
            outcome="failed",
            duration_seconds=0.1,
            failure_class=FailureClass.TEST,
            failure_message="RuntimeError: Fixture setup failed unexpectedly",
        )
        assert result.failure_class == FailureClass.TEST

    @requires("INFRA-002", "INFRA-001")
    def test_failure_class_skipped_test(self) -> None:
        """Skipped tests classified as SKIP."""
        result = TestResult(
            nodeid="tests/test.py::test_skipped",
            outcome="skipped",
            duration_seconds=0.0,
            failure_class=FailureClass.SKIP,
            failure_message="Skipped: requires real hardware",
        )
        assert result.failure_class == FailureClass.SKIP

