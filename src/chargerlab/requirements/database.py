"""Requirements database and traceability tracking.

Provides in-memory requirements database with test → requirement linking,
evidence collection, and compliance report generation.
"""

from dataclasses import dataclass, field  # Dataclass for simple structured data
from typing import Dict, List, Optional  # Type hints for function signatures
from enum import Enum  # Enumeration for requirement status
from datetime import datetime  # Timestamp tracking for evidence


class RequirementStatus(Enum):
    """Enumeration of requirement statuses in compliance workflow."""

    NOT_IMPLEMENTED = "not_implemented"  # Requirement not yet tested or implemented
    PENDING = "pending"  # Requirement has tests but results not collected
    PASSING = "passing"  # All linked tests passing
    FAILING = "failing"  # One or more linked tests failing
    PARTIAL = "partial"  # Some tests passing, some failing
    WAIVED = "waived"  # Requirement exempted from compliance


@dataclass
class Evidence:
    """Single piece of test evidence supporting a requirement."""

    test_name: str  # Name of test that generated this evidence
    timestamp: datetime  # When test ran and evidence was collected
    status: str  # "passed" or "failed" or "skipped"
    log_excerpt: str  # Key portion of test log output
    assertion_msg: Optional[str] = None  # Assertion message if failed


@dataclass
class Requirement:
    """Single requirement definition with traceability metadata."""

    requirement_id: str  # Unique identifier: REQ-001, REQ-002, etc.
    title: str  # Short human-readable title
    description: str  # Detailed requirement description
    category: str  # "safety", "functional", "interoperability", "performance"
    status: RequirementStatus = RequirementStatus.NOT_IMPLEMENTED  # Current compliance status
    linked_tests: List[str] = field(default_factory=list)  # Test names covering this requirement
    evidence: List[Evidence] = field(default_factory=list)  # Test results collected as evidence
    rationale: Optional[str] = None  # Why this requirement exists
    waiver_reason: Optional[str] = None  # If waived, explanation why


class RequirementsDatabase:
    """Central registry of all requirements with test traceability."""

    def __init__(self):  # Constructor initializes empty requirement storage
        self.requirements: Dict[str, Requirement] = {}  # Map requirement_id → Requirement object

    def add_requirement(
        self,
        requirement_id: str,
        title: str,
        description: str,
        category: str,
        rationale: Optional[str] = None,
    ) -> Requirement:
        """Register a new requirement in the database.

        Args:
            requirement_id: Unique ID like "REQ-001"
            title: Short human-readable title
            description: Detailed description of what must be tested
            category: "safety", "functional", "interoperability", "performance"
            rationale: Optional explanation of why requirement exists

        Returns:
            Newly created Requirement object
        """

        # Check for duplicate requirement ID before adding  (prevent accidental overwrites)
        if requirement_id in self.requirements:
            raise ValueError(f"Requirement {requirement_id} already exists")

        # Create requirement object with provided metadata
        req = Requirement(
            requirement_id=requirement_id,
            title=title,
            description=description,
            category=category,
            rationale=rationale,
        )

        # Store requirement in database by ID for fast lookup
        self.requirements[requirement_id] = req

        # Return reference so caller can use it immediately
        return req

    def link_test(self, requirement_id: str, test_name: str) -> None:
        """Associate a test with a requirement.

        Args:
            requirement_id: ID of requirement being tested
            test_name: Name of test covering this requirement

        Raises:
            KeyError: If requirement_id does not exist
        """

        # Look up requirement by ID, raise KeyError if not found
        if requirement_id not in self.requirements:
            raise KeyError(f"Requirement {requirement_id} not found")

        # Get requirement object for modification
        req = self.requirements[requirement_id]

        # Add test to linked tests if not already present (avoid duplicates)
        if test_name not in req.linked_tests:
            req.linked_tests.append(test_name)

    def record_evidence(
        self,
        requirement_id: str,
        test_name: str,
        status: str,
        log_excerpt: str,
        assertion_msg: Optional[str] = None,
    ) -> None:
        """Record test evidence supporting a requirement.

        Args:
            requirement_id: ID of requirement being tested
            test_name: Name of test that ran
            status: "passed", "failed", or "skipped"
            log_excerpt: Key portion of test output
            assertion_msg: Optional assertion message from failure

        Raises:
            KeyError: If requirement_id does not exist
        """

        # Look up requirement, raise KeyError if not found
        if requirement_id not in self.requirements:
            raise KeyError(f"Requirement {requirement_id} not found")

        # Get requirement object for modification
        req = self.requirements[requirement_id]

        # Create evidence object with current timestamp
        evidence = Evidence(
            test_name=test_name,
            timestamp=datetime.now(),  # Record when evidence was collected
            status=status,  # "passed", "failed", or "skipped"
            log_excerpt=log_excerpt,  # Key output from test
            assertion_msg=assertion_msg,  # Optional failure message
        )

        # Append evidence to requirement's evidence list
        req.evidence.append(evidence)

    def update_status(self, requirement_id: str) -> RequirementStatus:
        """Recalculate requirement status based on linked test results.

        Examines all evidence for the requirement and determines overall
        compliance status: PASSING, FAILING, PARTIAL, or PENDING.

        Args:
            requirement_id: ID of requirement to update

        Returns:
            Updated RequirementStatus

        Raises:
            KeyError: If requirement_id does not exist
        """

        # Look up requirement, raise KeyError if not found
        if requirement_id not in self.requirements:
            raise KeyError(f"Requirement {requirement_id} not found")

        # Get requirement object for analysis
        req = self.requirements[requirement_id]

        # If no evidence collected yet, status is PENDING
        if not req.evidence:
            req.status = RequirementStatus.PENDING
            return req.status

        # Count passing and failing evidence entries
        passed_count = sum(1 for e in req.evidence if e.status == "passed")
        failed_count = sum(1 for e in req.evidence if e.status == "failed")

        # If all evidence shows passing, status is PASSING
        if failed_count == 0 and passed_count > 0:
            req.status = RequirementStatus.PASSING

        # If any evidence shows failing, check if all failed
        elif failed_count > 0 and passed_count == 0:
            req.status = RequirementStatus.FAILING

        # If mix of passing and failing, status is PARTIAL
        elif failed_count > 0 and passed_count > 0:
            req.status = RequirementStatus.PARTIAL

        # Return updated status
        return req.status

    def waive_requirement(self, requirement_id: str, reason: str) -> None:
        """Waive a requirement from compliance tracking.

        Args:
            requirement_id: ID of requirement to waive
            reason: Explanation of why requirement is waived

        Raises:
            KeyError: If requirement_id does not exist
        """

        # Look up requirement, raise KeyError if not found
        if requirement_id not in self.requirements:
            raise KeyError(f"Requirement {requirement_id} not found")

        # Get requirement object for modification
        req = self.requirements[requirement_id]

        # Set status to WAIVED and record reason
        req.status = RequirementStatus.WAIVED
        req.waiver_reason = reason

    def get_requirement(self, requirement_id: str) -> Optional[Requirement]:
        """Retrieve a requirement by ID.

        Args:
            requirement_id: ID of requirement to lookup

        Returns:
            Requirement object or None if not found
        """

        # Look up requirement in dictionary, return None if not found
        return self.requirements.get(requirement_id)

    def get_by_category(self, category: str) -> List[Requirement]:
        """Retrieve all requirements in a specific category.

        Args:
            category: Category to filter by ("safety", "functional", etc.)

        Returns:
            List of Requirements matching the category
        """

        # Filter requirements by category match
        return [r for r in self.requirements.values() if r.category == category]

    def get_by_status(self, status: RequirementStatus) -> List[Requirement]:
        """Retrieve all requirements with a specific status.

        Args:
            status: RequirementStatus to filter by

        Returns:
            List of Requirements with matching status
        """

        # Filter requirements by exact status match
        return [r for r in self.requirements.values() if r.status == status]

    def get_coverage_summary(self) -> Dict[str, int]:
        """Get summary counts of requirements by status.

        Returns:
            Dictionary mapping status names to counts
        """

        # Initialize counter for each status value
        summary = {status.value: 0 for status in RequirementStatus}

        # Count requirements for each status
        for req in self.requirements.values():
            summary[req.status.value] += 1

        # Return populated counter dictionary
        return summary

    def get_failing_requirements(self) -> List[Requirement]:
        """Get all requirements that are currently failing.

        Returns:
            List of Requirements with FAILING or PARTIAL status
        """

        # Filter for requirements that are either FAILING or PARTIAL
        return [
            r
            for r in self.requirements.values()
            if r.status in (RequirementStatus.FAILING, RequirementStatus.PARTIAL)
        ]


# Global singleton instance used by pytest plugin and tests
_global_database: Optional[RequirementsDatabase] = None


def get_database() -> RequirementsDatabase:
    """Get or create global requirements database.

    Returns:
        Singleton RequirementsDatabase instance
    """

    global _global_database  # Access global variable for persistence

    # If no database exists yet, create one
    if _global_database is None:
        _global_database = RequirementsDatabase()

    # Return the singleton instance
    return _global_database


def reset_database() -> None:
    """Reset global database (mainly for testing).

    This clears all requirements and evidence, useful for test isolation.
    """

    global _global_database  # Access global variable for modification

    # Create new empty database, discarding old one
    _global_database = RequirementsDatabase()
