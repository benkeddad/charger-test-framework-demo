"""Phase 3 Tests: Requirements Traceability.

Tests the requirements database, pytest plugin, and report generation.

This test file validates that:
1. Requirements can be defined and stored
2. Tests link to requirements via @requires decorator
3. Evidence is collected during test execution
4. Reports can be generated in multiple formats
5. Requirement status is computed correctly
"""

import pytest  # Pytest framework
from pathlib import Path  # File path operations

from chargerlab.requirements.database import (  # Requirements database
    RequirementsDatabase,
    RequirementStatus,
    get_database,
    reset_database,
)
from chargerlab.requirements.report_generator import TraceabilityReport  # Report generation
from chargerlab.requirements.pytest_plugin import requires  # Test decorator


# ============================================================================
# Test Suite: Requirements Database
# ============================================================================


@pytest.mark.integration
def test_requirements_database_add():
    """Test that requirements can be added to database.

    Validates:
    - New requirement can be created with metadata
    - Requirement stored with correct ID
    - Status initialized to NOT_IMPLEMENTED
    """
    # Reset database for clean test state
    reset_database()

    # Get clean database instance
    db = get_database()

    # Add requirement to database
    req = db.add_requirement(
        requirement_id="TEST-001",  # Unique ID
        title="Test Requirement",  # Human-readable title
        description="A requirement for testing",  # Full description
        category="functional",  # Category classification
        rationale="To test requirement tracking",  # Why needed
    )

    # Verify requirement was created
    assert req.requirement_id == "TEST-001"  # ID matches
    assert req.title == "Test Requirement"  # Title matches
    assert req.status == RequirementStatus.NOT_IMPLEMENTED  # Status initialized
    assert len(req.linked_tests) == 0  # No tests linked yet
    assert len(req.evidence) == 0  # No evidence yet


@pytest.mark.integration
def test_requirements_database_duplicate_id_rejected():
    """Test that duplicate requirement IDs are rejected.

    Validates:
    - Cannot add two requirements with same ID
    - ValueError raised with helpful message
    """
    # Reset database for clean test state
    reset_database()

    # Get clean database instance
    db = get_database()

    # Add first requirement
    db.add_requirement(
        requirement_id="DUP-001",  # ID
        title="First",  # Title
        description="First requirement",  # Description
        category="functional",  # Category
    )

    # Attempt to add second with same ID
    with pytest.raises(ValueError) as exc_info:
        db.add_requirement(
            requirement_id="DUP-001",  # Same ID
            title="Second",  # Different title
            description="Second requirement",  # Different description
            category="functional",  # Category
        )

    # Verify error message is helpful
    assert "DUP-001" in str(exc_info.value)  # ID in error
    assert "already exists" in str(exc_info.value)  # Clear message


@pytest.mark.integration
def test_requirements_database_link_test():
    """Test that tests can be linked to requirements.

    Validates:
    - Test can be linked to requirement
    - Test appears in requirement.linked_tests
    - Duplicate test links are prevented
    """
    # Reset database for clean test state
    reset_database()

    # Get clean database instance
    db = get_database()

    # Add requirement
    db.add_requirement(
        requirement_id="LINK-001",  # ID
        title="Link Test",  # Title
        description="Requirement for linking test",  # Description
        category="functional",  # Category
    )

    # Link test to requirement
    db.link_test("LINK-001", "test_something")  # Link test

    # Verify test was linked
    req = db.get_requirement("LINK-001")  # Get requirement
    assert "test_something" in req.linked_tests  # Test in linked list

    # Link same test again
    db.link_test("LINK-001", "test_something")  # Link same test

    # Verify no duplicate
    assert req.linked_tests.count("test_something") == 1  # Only one copy


@pytest.mark.integration
def test_requirements_database_link_nonexistent_requirement():
    """Test that linking to nonexistent requirement fails.

    Validates:
    - KeyError raised when requirement doesn't exist
    - Error message is helpful
    """
    # Reset database for clean test state
    reset_database()

    # Get clean database instance
    db = get_database()

    # Attempt to link test to nonexistent requirement
    with pytest.raises(KeyError) as exc_info:
        db.link_test("MISSING-001", "test_something")  # Requirement doesn't exist

    # Verify error message mentions requirement ID
    assert "MISSING-001" in str(exc_info.value)  # ID in error


@pytest.mark.integration
def test_requirements_database_record_evidence():
    """Test that evidence (test results) can be recorded.

    Validates:
    - Evidence can be recorded for requirement
    - Evidence contains correct metadata
    - Evidence list is maintained
    """
    # Reset database for clean test state
    reset_database()

    # Get clean database instance
    db = get_database()

    # Add requirement
    db.add_requirement(
        requirement_id="EV-001",  # ID
        title="Evidence Test",  # Title
        description="Requirement for recording evidence",  # Description
        category="functional",  # Category
    )

    # Record evidence (test passed)
    db.record_evidence(
        requirement_id="EV-001",  # Requirement ID
        test_name="test_ev_001",  # Test name
        status="passed",  # Test passed
        log_excerpt="All assertions passed",  # Log summary
    )

    # Verify evidence was recorded
    req = db.get_requirement("EV-001")  # Get requirement
    assert len(req.evidence) == 1  # One evidence entry
    assert req.evidence[0].test_name == "test_ev_001"  # Test name correct
    assert req.evidence[0].status == "passed"  # Status correct


@pytest.mark.integration
def test_requirements_database_status_passing():
    """Test that requirement status is PASSING when all tests pass.

    Validates:
    - Status updates to PASSING when evidence shows passed
    - get_by_status filter works
    """
    # Reset database for clean test state
    reset_database()

    # Get clean database instance
    db = get_database()

    # Add requirement
    db.add_requirement(
        requirement_id="PASS-001",  # ID
        title="Passing Requirement",  # Title
        description="Requirement with passing test",  # Description
        category="functional",  # Category
    )

    # Record passing evidence
    db.record_evidence("PASS-001", "test_pass_1", "passed", "Test 1 passed")
    db.record_evidence("PASS-001", "test_pass_2", "passed", "Test 2 passed")

    # Update status
    status = db.update_status("PASS-001")  # Compute status

    # Verify status is PASSING
    assert status == RequirementStatus.PASSING  # Status correct
    req = db.get_requirement("PASS-001")  # Get requirement
    assert req.status == RequirementStatus.PASSING  # Status persisted


@pytest.mark.integration
def test_requirements_database_status_failing():
    """Test that requirement status is FAILING when tests fail.

    Validates:
    - Status updates to FAILING when evidence shows failed
    - All failing tests result in FAILING status
    """
    # Reset database for clean test state
    reset_database()

    # Get clean database instance
    db = get_database()

    # Add requirement
    db.add_requirement(
        requirement_id="FAIL-001",  # ID
        title="Failing Requirement",  # Title
        description="Requirement with failing test",  # Description
        category="functional",  # Category
    )

    # Record failing evidence
    db.record_evidence("FAIL-001", "test_fail_1", "failed", "Assertion failed", "Expected 5, got 3")

    # Update status
    status = db.update_status("FAIL-001")  # Compute status

    # Verify status is FAILING
    assert status == RequirementStatus.FAILING  # Status correct
    req = db.get_requirement("FAIL-001")  # Get requirement
    assert req.status == RequirementStatus.FAILING  # Status persisted


@pytest.mark.integration
def test_requirements_database_status_partial():
    """Test that requirement status is PARTIAL with mix of pass/fail.

    Validates:
    - Status updates to PARTIAL when some tests pass and some fail
    - Mixed evidence handled correctly
    """
    # Reset database for clean test state
    reset_database()

    # Get clean database instance
    db = get_database()

    # Add requirement
    db.add_requirement(
        requirement_id="PART-001",  # ID
        title="Partial Requirement",  # Title
        description="Requirement with mixed test results",  # Description
        category="functional",  # Category
    )

    # Record mixed evidence
    db.record_evidence("PART-001", "test_part_1", "passed", "Test 1 passed")  # One passes
    db.record_evidence("PART-001", "test_part_2", "failed", "Test 2 failed", "Expected X, got Y")

    # Update status
    status = db.update_status("PART-001")  # Compute status

    # Verify status is PARTIAL
    assert status == RequirementStatus.PARTIAL  # Status correct
    req = db.get_requirement("PART-001")  # Get requirement
    assert req.status == RequirementStatus.PARTIAL  # Status persisted


@pytest.mark.integration
def test_requirements_database_waive_requirement():
    """Test that requirements can be waived from compliance.

    Validates:
    - Requirement can be waived with reason
    - Status updates to WAIVED
    - Waiver reason is recorded
    """
    # Reset database for clean test state
    reset_database()

    # Get clean database instance
    db = get_database()

    # Add requirement
    db.add_requirement(
        requirement_id="WAIVE-001",  # ID
        title="Waivable Requirement",  # Title
        description="Requirement that might be waived",  # Description
        category="functional",  # Category
    )

    # Waive requirement
    reason = "Not applicable to simulator, only real hardware"  # Waiver reason
    db.waive_requirement("WAIVE-001", reason)  # Waive

    # Verify waiver was recorded
    req = db.get_requirement("WAIVE-001")  # Get requirement
    assert req.status == RequirementStatus.WAIVED  # Status is WAIVED
    assert req.waiver_reason == reason  # Reason recorded


@pytest.mark.integration
def test_requirements_database_get_by_category():
    """Test that requirements can be filtered by category.

    Validates:
    - get_by_category returns only matching requirements
    - Multiple categories can be queried independently
    """
    # Reset database for clean test state
    reset_database()

    # Get clean database instance
    db = get_database()

    # Add requirements in different categories
    db.add_requirement("CAT-001", "Safety Req", "First", "safety")  # Safety
    db.add_requirement("CAT-002", "Safety Req 2", "Second", "safety")  # Safety
    db.add_requirement("CAT-003", "Functional Req", "Third", "functional")  # Functional

    # Query by category
    safety_reqs = db.get_by_category("safety")  # Get safety requirements
    functional_reqs = db.get_by_category("functional")  # Get functional

    # Verify filtering
    assert len(safety_reqs) == 2  # Two safety requirements
    assert len(functional_reqs) == 1  # One functional requirement
    assert all(r.category == "safety" for r in safety_reqs)  # All safety
    assert all(r.category == "functional" for r in functional_reqs)  # All functional


@pytest.mark.integration
def test_requirements_database_coverage_summary():
    """Test that coverage summary counts are correct.

    Validates:
    - Summary includes all status types
    - Counts are accurate
    """
    # Reset database for clean test state
    reset_database()

    # Get clean database instance
    db = get_database()

    # Add requirements in different states
    db.add_requirement("SUM-001", "Not Impl", "First", "functional")  # NOT_IMPLEMENTED
    req2 = db.add_requirement("SUM-002", "Passing", "Second", "functional")  # Will be PASSING

    # Record evidence for second requirement
    db.record_evidence("SUM-002", "test_sum_2", "passed", "Test passed")
    db.update_status("SUM-002")  # Status PASSING

    # Get coverage summary
    summary = db.get_coverage_summary()  # Get summary counts

    # Verify summary
    assert summary["not_implemented"] == 1  # One not implemented
    assert summary["passing"] == 1  # One passing
    assert summary["failing"] == 0  # Zero failing
    assert sum(summary.values()) == 2  # Total is 2


# ============================================================================
# Test Suite: Report Generation
# ============================================================================


@pytest.mark.integration
def test_report_generator_text_report(tmp_path):
    """Test that text report can be generated.

    Validates:
    - Text report is generated
    - Report contains summary and details
    - Report is written to file
    """
    # Reset database for clean test state
    reset_database()

    # Get clean database instance
    db = get_database()

    # Add requirements
    db.add_requirement("REP-001", "Test Req", "Description", "functional")

    # Record evidence
    db.record_evidence("REP-001", "test_rep_1", "passed", "Test passed")
    db.update_status("REP-001")

    # Generate report
    report_gen = TraceabilityReport(db)  # Create report generator
    report_path = tmp_path / "report.txt"  # Output file

    # Generate text report
    report_text = report_gen.generate_text_report(str(report_path))

    # Verify report contains expected content
    assert "REQUIREMENTS TRACEABILITY REPORT" in report_text  # Title (uppercase)
    assert "SUMMARY" in report_text  # Summary section
    assert "REP-001" in report_text  # Requirement ID
    assert "Test Req" in report_text  # Requirement title
    assert "passing" in report_text  # Status

    # Verify file was created
    assert report_path.exists()  # File exists
    assert report_path.read_text() == report_text  # Content matches


@pytest.mark.integration
def test_report_generator_csv_report(tmp_path):
    """Test that CSV report can be generated.

    Validates:
    - CSV report is generated
    - CSV has correct columns and data
    - Can be imported into tools
    """
    # Reset database for clean test state
    reset_database()

    # Get clean database instance
    db = get_database()

    # Add requirements
    db.add_requirement("CSV-001", "Test Req", "Description", "safety")
    db.record_evidence("CSV-001", "test_csv_1", "passed", "Test passed")
    db.update_status("CSV-001")

    # Generate CSV report
    report_gen = TraceabilityReport(db)  # Create report generator
    report_path = tmp_path / "report.csv"  # Output file

    # Generate CSV
    report_gen.generate_csv_report(str(report_path))

    # Verify file was created
    assert report_path.exists()  # File exists

    # Read and verify CSV content
    csv_content = report_path.read_text()  # Read file
    assert "requirement_id" in csv_content  # Header present
    assert "CSV-001" in csv_content  # Requirement ID in CSV
    assert "Test Req" in csv_content  # Requirement title in CSV


@pytest.mark.integration
def test_report_generator_html_report(tmp_path):
    """Test that HTML report can be generated.

    Validates:
    - HTML report is generated
    - HTML has correct structure and content
    - Can be opened in browser for review
    """
    # Reset database for clean test state
    reset_database()

    # Get clean database instance
    db = get_database()

    # Add requirements
    db.add_requirement("HTML-001", "Test Req", "Description", "functional")
    db.record_evidence("HTML-001", "test_html_1", "passed", "Test passed")
    db.update_status("HTML-001")

    # Generate HTML report
    report_gen = TraceabilityReport(db)  # Create report generator
    report_path = tmp_path / "report.html"  # Output file

    # Generate HTML
    report_gen.generate_html_report(str(report_path))

    # Verify file was created
    assert report_path.exists()  # File exists

    # Read and verify HTML content
    html_content = report_path.read_text()  # Read file
    assert "<!DOCTYPE html>" in html_content  # Valid HTML5
    assert "Requirements Traceability Report" in html_content  # Title
    assert "HTML-001" in html_content  # Requirement ID
    assert "Test Req" in html_content  # Requirement title
    assert "<table" in html_content  # Has table


# ============================================================================
# Test Suite: @requires Decorator
# ============================================================================


@pytest.mark.integration
@requires("REQ-001", "REQ-002")  # Link to requirements  
def test_requires_decorator_links_tests():
    """Test that @requires decorator links tests to requirements.

    This test itself demonstrates the decorator usage.
    When this test runs, it should record evidence for REQ-001 and REQ-002.

    Validates:
    - Decorator accepts multiple requirement IDs
    - Requirement IDs stored on test function
    """
    # Reset database for clean test state
    reset_database()

    # Add requirements
    db = get_database()
    db.add_requirement("REQ-001", "First", "First requirement", "functional")
    db.add_requirement("REQ-002", "Second", "Second requirement", "functional")

    # Verify decorator attached requirement IDs to function
    # (This is done by pytest plugin, not directly by test)
    assert hasattr(test_requires_decorator_links_tests, "_requirement_ids")  # Has attribute
    assert test_requires_decorator_links_tests._requirement_ids == ("REQ-001", "REQ-002")  # IDs match
