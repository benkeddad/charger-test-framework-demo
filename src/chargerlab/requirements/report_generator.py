"""Report generation for requirements traceability.

Generates compliance reports in multiple formats:
- Text: Human-readable summary and detailed coverage
- CSV: For import into requirement management tools
- HTML: For stakeholder review and archival
"""

import csv  # CSV file generation
from datetime import datetime  # Timestamp formatting
from typing import Dict, List, Optional  # Type hints for functions
from pathlib import Path  # File path operations
from chargerlab.requirements.database import (  # Access requirements DB
    RequirementsDatabase,
    RequirementStatus,
)


class TraceabilityReport:
    """Generates compliance and traceability reports from requirements database."""

    def __init__(self, database: RequirementsDatabase):  # Constructor stores database reference
        self.database = database  # Reference to requirements database

    def generate_text_report(self, filepath: Optional[str] = None) -> str:
        """Generate human-readable text report.

        Summary section shows requirement counts by status.
        Detail section lists each requirement with test coverage.

        Args:
            filepath: Optional path to write report to file

        Returns:
            Report text (also written to file if filepath provided)
        """

        lines = []  # List to accumulate report lines
        lines.append("=" * 80)  # Top border
        lines.append("REQUIREMENTS TRACEABILITY REPORT")  # Title
        lines.append("=" * 80)  # Border
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")  # Timestamp
        lines.append("")  # Blank line for readability

        # SUMMARY SECTION
        lines.append("SUMMARY")  # Section heading
        lines.append("-" * 80)  # Section border

        # Get coverage counts by status
        summary = self.database.get_coverage_summary()

        # Display count for each status
        total_reqs = sum(summary.values())  # Total requirements count
        lines.append(f"Total Requirements: {total_reqs}")  # Total count
        lines.append(f"  Passing:          {summary['passing']}")  # Count by status
        lines.append(f"  Failing:          {summary['failing']}")
        lines.append(f"  Partial:          {summary['partial']}")
        lines.append(f"  Pending:          {summary['pending']}")
        lines.append(f"  Not Implemented:  {summary['not_implemented']}")
        lines.append(f"  Waived:           {summary['waived']}")
        lines.append("")  # Blank line

        # FAILING REQUIREMENTS SECTION
        failing = self.database.get_failing_requirements()  # Get FAILING and PARTIAL
        if failing:
            lines.append("FAILING REQUIREMENTS")  # Section heading
            lines.append("-" * 80)  # Section border

            # List each failing requirement with details
            for req in failing:
                lines.append(f"{req.requirement_id}: {req.title}")  # ID and title
                lines.append(f"  Status: {req.status.value}")  # Current status
                lines.append(f"  Linked Tests: {', '.join(req.linked_tests) if req.linked_tests else 'None'}")  # Tests
                lines.append(f"  Evidence:")  # Evidence section
                for evidence in req.evidence:
                    # Show each test result
                    lines.append(f"    - {evidence.test_name}: {evidence.status}")

                lines.append("")  # Blank line between requirements

        # DETAIL SECTION
        lines.append("DETAILED REQUIREMENTS")  # Section heading
        lines.append("-" * 80)  # Section border

        # Sort requirements by ID for consistent ordering
        sorted_reqs = sorted(
            self.database.requirements.values(), key=lambda r: r.requirement_id
        )

        # List each requirement with full details
        for req in sorted_reqs:
            lines.append(f"{req.requirement_id}: {req.title}")  # ID and title
            lines.append(f"  Category:     {req.category}")  # Requirement category
            lines.append(f"  Status:       {req.status.value}")  # Current status
            lines.append(f"  Description:  {req.description}")  # Full description
            if req.rationale:
                lines.append(f"  Rationale:    {req.rationale}")  # Why requirement exists
            if req.waiver_reason:
                lines.append(f"  Waiver:       {req.waiver_reason}")  # Why waived

            # Show linked tests
            if req.linked_tests:
                lines.append(f"  Linked Tests:")  # Test section heading
                for test in req.linked_tests:
                    lines.append(f"    - {test}")  # Test name

            # Show evidence (test results)
            if req.evidence:
                lines.append(f"  Evidence:")  # Evidence section heading
                for evidence in req.evidence:
                    lines.append(f"    - {evidence.test_name}: {evidence.status}")  # Result
                    lines.append(f"      {evidence.log_excerpt}")  # Log excerpt

            lines.append("")  # Blank line between requirements

        lines.append("=" * 80)  # Bottom border

        # Join all lines into single report string
        report_text = "\n".join(lines)

        # Write to file if filepath provided
        if filepath:
            with open(filepath, "w") as f:
                f.write(report_text)

        # Return report text
        return report_text

    def generate_csv_report(self, filepath: str) -> None:
        """Generate CSV report for import into requirement tools.

        CSV columns: requirement_id, title, category, status,
        linked_tests_count, evidence_count, passing_tests, failing_tests

        Args:
            filepath: Path to write CSV file to
        """

        # Open CSV file for writing
        with open(filepath, "w", newline="") as csvfile:
            # Define CSV columns
            fieldnames = [
                "requirement_id",  # Unique requirement ID
                "title",  # Human-readable title
                "category",  # Category classification
                "status",  # Current compliance status
                "linked_tests_count",  # Number of linked tests
                "evidence_count",  # Total evidence entries
                "passing_tests",  # Count of passing evidence
                "failing_tests",  # Count of failing evidence
            ]

            # Create CSV writer with fieldnames
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            # Write header row with column names
            writer.writeheader()

            # Sort requirements by ID for consistent ordering
            sorted_reqs = sorted(
                self.database.requirements.values(), key=lambda r: r.requirement_id
            )

            # Write each requirement as CSV row
            for req in sorted_reqs:
                # Count passing and failing evidence
                passing = sum(1 for e in req.evidence if e.status == "passed")
                failing = sum(1 for e in req.evidence if e.status == "failed")

                # Write requirement as row
                writer.writerow(
                    {
                        "requirement_id": req.requirement_id,  # ID
                        "title": req.title,  # Title
                        "category": req.category,  # Category
                        "status": req.status.value,  # Status
                        "linked_tests_count": len(req.linked_tests),  # Test count
                        "evidence_count": len(req.evidence),  # Evidence count
                        "passing_tests": passing,  # Passing count
                        "failing_tests": failing,  # Failing count
                    }
                )

    def generate_html_report(self, filepath: str) -> None:
        """Generate HTML report for stakeholder review.

        Creates styled HTML with summary table, status indicators,
        and collapsible detail sections.

        Args:
            filepath: Path to write HTML file to
        """

        # Start HTML document
        html_parts = []
        html_parts.append("<!DOCTYPE html>")  # HTML5 doctype
        html_parts.append("<html>")  # Root element
        html_parts.append("<head>")  # Document header
        html_parts.append("<meta charset='UTF-8'>")  # Character encoding
        html_parts.append("<title>Requirements Traceability Report</title>")  # Page title
        html_parts.append("<style>")  # Style section

        # Embed CSS styles for nice formatting
        html_parts.append("""
            body { font-family: Arial, sans-serif; margin: 20px; }
            h1 { color: #333; border-bottom: 2px solid #333; }
            h2 { color: #666; margin-top: 30px; }
            .summary { background: #f5f5f5; padding: 15px; border-radius: 5px; }
            .summary-table { width: 100%; border-collapse: collapse; }
            .summary-table td { padding: 8px; border: 1px solid #ddd; }
            .requirement { margin: 20px 0; padding: 15px; background: #fafafa; border-left: 4px solid #007bff; }
            .status-passing { color: green; font-weight: bold; }
            .status-failing { color: red; font-weight: bold; }
            .status-partial { color: orange; font-weight: bold; }
            .status-pending { color: blue; font-weight: bold; }
            .evidence { margin: 10px 0; padding: 10px; background: #fff; border: 1px solid #ddd; }
            .evidence-passed { border-left: 3px solid green; }
            .evidence-failed { border-left: 3px solid red; }
            .timestamp { color: #999; font-size: 0.9em; }
        """)

        html_parts.append("</style>")  # End style section
        html_parts.append("</head>")  # End header
        html_parts.append("<body>")  # Body content starts

        # Title and timestamp
        html_parts.append("<h1>Requirements Traceability Report</h1>")  # Main title
        html_parts.append(f"<p class='timestamp'>Generated: {datetime.now()}</p>")  # Timestamp

        # Summary section
        html_parts.append("<h2>Summary</h2>")  # Summary heading
        summary = self.database.get_coverage_summary()  # Get status counts
        html_parts.append("<div class='summary'>")  # Summary container
        html_parts.append("<table class='summary-table'>")  # Summary table

        # Add row for each status
        html_parts.append(f"<tr><td>Total Requirements</td><td>{sum(summary.values())}</td></tr>")
        html_parts.append(f"<tr><td>Passing</td><td class='status-passing'>{summary['passing']}</td></tr>")
        html_parts.append(f"<tr><td>Failing</td><td class='status-failing'>{summary['failing']}</td></tr>")
        html_parts.append(f"<tr><td>Partial</td><td class='status-partial'>{summary['partial']}</td></tr>")
        html_parts.append(f"<tr><td>Pending</td><td class='status-pending'>{summary['pending']}</td></tr>")

        html_parts.append("</table>")  # End table
        html_parts.append("</div>")  # End summary container

        # Detailed requirements section
        html_parts.append("<h2>Requirements</h2>")  # Detail heading
        sorted_reqs = sorted(
            self.database.requirements.values(), key=lambda r: r.requirement_id
        )

        # Add each requirement
        for req in sorted_reqs:
            # Determine status class for styling
            status_class = f"status-{req.status.value.replace('_', '-')}"

            # Requirement container
            html_parts.append("<div class='requirement'>")  # Container

            # Requirement ID and title
            html_parts.append(f"<h3>{req.requirement_id}: {req.title}</h3>")  # Heading

            # Status and category
            html_parts.append(f"<p><strong>Status:</strong> <span class='{status_class}'>{req.status.value}</span></p>")
            html_parts.append(f"<p><strong>Category:</strong> {req.category}</p>")  # Category
            html_parts.append(f"<p><strong>Description:</strong> {req.description}</p>")  # Description

            # Linked tests
            if req.linked_tests:
                html_parts.append("<p><strong>Linked Tests:</strong></p>")  # Tests heading
                html_parts.append("<ul>")  # Test list
                for test in req.linked_tests:
                    html_parts.append(f"<li>{test}</li>")  # Test item
                html_parts.append("</ul>")  # End list

            # Evidence
            if req.evidence:
                html_parts.append("<p><strong>Evidence:</strong></p>")  # Evidence heading
                for evidence in req.evidence:
                    # Determine evidence CSS class
                    evidence_class = f"evidence evidence-{evidence.status}"
                    html_parts.append(f"<div class='{evidence_class}'>")  # Evidence container

                    # Test result
                    html_parts.append(f"<strong>{evidence.test_name}</strong>: {evidence.status}")  # Name and status
                    html_parts.append(f"<p>{evidence.log_excerpt}</p>")  # Log excerpt
                    html_parts.append(f"<p class='timestamp'>{evidence.timestamp}</p>")  # Timestamp

                    html_parts.append("</div>")  # End evidence

            html_parts.append("</div>")  # End requirement

        # Close HTML document
        html_parts.append("</body>")  # End body
        html_parts.append("</html>")  # End document

        # Join HTML and write to file
        html_text = "\n".join(html_parts)
        with open(filepath, "w") as f:
            f.write(html_text)
