"""Pytest plugin for requirements traceability.

Provides @requires decorator for linking tests to requirements,
hooks into test execution to collect evidence, and generates
compliance reports.

Usage:
    @requires("REQ-001", "REQ-002")  # Can link multiple requirements
    async def test_something(charger):
        ...
"""

import pytest  # Pytest framework for hooks and fixtures
from typing import Optional, Callable, Any, Dict  # Type hints for decorators
from functools import wraps  # Decorator composition helper
from chargerlab.requirements.database import get_database  # Access requirements DB


def requires(*requirement_ids: str):
    """Decorator to link a test to one or more requirements.

    When a test decorated with @requires runs, its results are
    automatically recorded in the requirements database as evidence.

    Args:
        *requirement_ids: Variable number of requirement IDs like "REQ-001"

    Returns:
        Decorator function that wraps the test

    Example:
        @requires("REQ-001", "REQ-002")
        async def test_charging_workflow(charger):
            assert charger.is_connected()
    """

    def decorator(func: Callable) -> Callable:
        """Inner decorator that wraps the test function.

        Args:
            func: The test function being decorated

        Returns:
            Wrapped function that executes test and records evidence
        """

        # Mark test function with requirement IDs for pytest to access
        func._requirement_ids = requirement_ids  # Store on function object

        # Return wrapped function (pass through to pytest, no behavior change)
        return func

    # Return decorator function to pytest
    return decorator


class RequirementsPlugin:
    """Pytest plugin that hooks into test execution lifecycle.

    Automatically links test results to requirements and collects
    evidence for compliance reporting.
    """

    def __init__(self):  # Constructor initializes plugin state
        self.database = get_database()  # Get global requirements database
        self.test_requirements: Dict[str, tuple] = {}  # Map test nodeid → requirement IDs

    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        """Hook called before each test runs.

        Args:
            item: pytest Item representing the test function
        """

        # Get requirement IDs from decorator if present on test function
        requirement_ids = getattr(item.function, "_requirement_ids", ())

        # Store requirement IDs indexed by test nodeid for later retrieval in logreport
        self.test_requirements[item.nodeid] = requirement_ids

        # Link each requirement to this test in the database
        for req_id in requirement_ids:
            try:
                # Link requirement to test by adding to linked_tests list
                self.database.link_test(req_id, item.name)
            except KeyError:
                # If requirement doesn't exist, skip (may be created later)
                pass

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        """Hook called when test execution completes.

        Records test results as evidence in the requirements database.

        Args:
            report: pytest TestReport with test execution details
        """

        # Only process completion reports (not setup/teardown)
        if report.when != "call":
            return

        # Get requirement IDs for this test using nodeid (stored in setup)
        requirement_ids = self.test_requirements.get(report.nodeid, ())

        # If no requirements linked, nothing to do
        if not requirement_ids:
            return

        # Determine test status from pytest outcome
        if report.passed:
            status = "passed"  # Test succeeded
            log_excerpt = "Test passed all assertions"  # Summary for evidence
        elif report.failed:
            status = "failed"  # Test failed
            # Extract failure message from exception info
            failure_msg = str(report.longrepr) if report.longrepr else "Unknown failure"
            # Use first line of failure as excerpt (keep it concise)
            log_excerpt = failure_msg.split("\n")[0][:200]
        else:
            status = "skipped"  # Test was skipped
            log_excerpt = "Test skipped"  # Reason for skip

        # Extract test name from nodeid (format: "path/to/file.py::test_name")
        test_name = report.nodeid.split("::")[-1]  # Get last part after ::

        # Record evidence for each linked requirement
        for req_id in requirement_ids:
            try:
                # Record test result as evidence supporting requirement
                self.database.record_evidence(
                    req_id,
                    test_name,  # Test name
                    status,  # "passed", "failed", or "skipped"
                    log_excerpt,  # Key output or error message
                    assertion_msg=log_excerpt,  # Same as log_excerpt for evidence
                )

                # Update requirement status based on new evidence
                self.database.update_status(req_id)

            except KeyError:
                # If requirement doesn't exist, skip (may not be registered yet)
                pass


def pytest_configure(config: pytest.Config) -> None:
    """Hook called at pytest startup.

    Registers the RequirementsPlugin with pytest so it receives
    test execution lifecycle events.

    Args:
        config: pytest Config object with configuration
    """

    # Instantiate plugin that will hook into test lifecycle
    plugin = RequirementsPlugin()

    # Register plugin with pytest so hooks are called
    config.pluginmanager.register(plugin, "requirements_plugin")
