"""Phase 3: Requirements Definitions and Setup.

This module defines all requirements for the charger test framework
and links them to test cases for compliance tracking.

Requirements are organized by category:
- Safety: Rules protecting hardware and personnel
- Functional: Core charger behavior
- Interoperability: OCPP and IEC 61851 compliance
- Performance: Speed and resource efficiency
"""

from chargerlab.requirements.database import get_database  # Access requirements DB


def setup_requirements() -> None:
    """Initialize requirements database with all Phase 1-3 requirements.

    This function is called during conftest setup to populate the database
    with requirements that tests will link to via @requires decorator.
    """

    db = get_database()  # Get global requirements database
    
    # Check if already initialized to prevent duplicate
    if db.requirements:  # If database has requirements, skip
        return

    # =================================================================
    # SAFETY REQUIREMENTS
    # =================================================================

    # REQ-001: Power supply isolation
    db.add_requirement(
        requirement_id="REQ-001",  # Unique identifier
        title="PSU output disabled in unsafe states",  # Human-readable title
        description="Power supply output must be OFF in IEC 61851 states A, B, E, F",  # Detailed description
        category="safety",  # Safety-critical requirement
        rationale="Prevents electrical hazard if vehicle not connected or authorized",  # Why required
    )

    # REQ-002: Voltage safety limits
    db.add_requirement(
        requirement_id="REQ-002",  # Unique identifier
        title="Voltage constrained by PSU max_voltage",  # Human-readable title
        description="Charger cannot set voltage higher than PSU max_voltage limit",  # Detailed description
        category="safety",  # Safety-critical requirement
        rationale="Protects vehicle battery and charging cable from overvoltage",  # Why required
    )

    # REQ-003: State machine enforcement
    db.add_requirement(
        requirement_id="REQ-003",  # Unique identifier
        title="IEC 61851 state transitions enforced",  # Human-readable title
        description="Only valid state transitions allowed; invalid transitions rejected",  # Detailed description
        category="safety",  # Safety-critical requirement
        rationale="Prevents charger operating in undefined or dangerous state combinations",  # Why required
    )

    # =================================================================
    # FUNCTIONAL REQUIREMENTS
    # =================================================================

    # REQ-004: OCPP connection and boot
    db.add_requirement(
        requirement_id="REQ-004",  # Unique identifier
        title="Charger connects to OCPP central system",  # Human-readable title
        description="Charger establishes WebSocket connection and sends BootNotification",  # Detailed description
        category="functional",  # Functional requirement
        rationale="OCPP 1.6J protocol requires boot handshake before any charging",  # Why required
    )

    # REQ-005: Authorization workflow
    db.add_requirement(
        requirement_id="REQ-005",  # Unique identifier
        title="Tag authorization before charging",  # Human-readable title
        description="Charger blocks StartTransaction until tag authorized",  # Detailed description
        category="functional",  # Functional requirement
        rationale="Access control: only authorized users can charge",  # Why required
    )

    # REQ-006: Transaction lifecycle
    db.add_requirement(
        requirement_id="REQ-006",  # Unique identifier
        title="StartTransaction and StopTransaction flow",  # Human-readable title
        description="Charger can start, track, and stop multiple consecutive transactions",  # Detailed description
        category="functional",  # Functional requirement
        rationale="Metering and billing requires accurate transaction boundaries",  # Why required
    )

    # REQ-007: Unique transaction IDs
    db.add_requirement(
        requirement_id="REQ-007",  # Unique identifier
        title="Each transaction has unique transactionId",  # Human-readable title
        description="No two transactions should have the same transactionId",  # Detailed description
        category="functional",  # Functional requirement
        rationale="Transaction ID is primary key for billing and accounting",  # Why required
    )

    # REQ-008: State transitions with authorization
    db.add_requirement(
        requirement_id="REQ-008",  # Unique identifier
        title="State C reached only after authorization",  # Human-readable title
        description="Charger moves to IEC 61851 state C (ready to deliver power) only after tag accepted",  # Detailed description
        category="functional",  # Functional requirement
        rationale="Prevents power delivery to unauthorized vehicle",  # Why required
    )

    # =================================================================
    # INTEROPERABILITY REQUIREMENTS
    # =================================================================

    # REQ-009: OCPP 1.6J compliance
    db.add_requirement(
        requirement_id="REQ-009",  # Unique identifier
        title="OCPP 1.6J message format compliance",  # Human-readable title
        description="All OCPP messages use correct array format: [type, msgId, payload]",  # Detailed description
        category="interoperability",  # Interoperability requirement
        rationale="OCPP 1.6J specification defines exact message format",  # Why required
    )

    # REQ-010: IEC 61851 state machine
    db.add_requirement(
        requirement_id="REQ-010",  # Unique identifier
        title="IEC 61851-1 state machine implementation",  # Human-readable title
        description="Charger implements state A→B→C transitions and power control per spec",  # Detailed description
        category="interoperability",  # Interoperability requirement
        rationale="IEC 61851 is international standard for EV charging control",  # Why required
    )

    # REQ-011: Multiple transaction support
    db.add_requirement(
        requirement_id="REQ-011",  # Unique identifier
        title="Support consecutive transactions",  # Human-readable title
        description="Charger correctly handles multiple tag auth/charge cycles",  # Detailed description
        category="interoperability",  # Interoperability requirement
        rationale="Real-world chargers serve multiple vehicles per day",  # Why required
    )

    # =================================================================
    # PERFORMANCE REQUIREMENTS
    # =================================================================

    # REQ-012: Test execution speed
    db.add_requirement(
        requirement_id="REQ-012",  # Unique identifier
        title="Integration test suite completes in < 1s",  # Human-readable title
        description="All 8 integration tests pass within 1 second total",  # Detailed description
        category="performance",  # Performance requirement
        rationale="Fast feedback loop enables rapid development iteration",  # Why required
    )

    # REQ-013: Deterministic test behavior
    db.add_requirement(
        requirement_id="REQ-013",  # Unique identifier
        title="Tests pass consistently without flakes",  # Human-readable title
        description="100% pass rate across 20+ consecutive test runs",  # Detailed description
        category="performance",  # Performance requirement
        rationale="Flaky tests reduce confidence and increase debugging cost",  # Why required
    )


def link_phase_1_tests() -> None:
    """Link Phase 1 tests to requirements.

    Phase 1 validates PowerSupply driver and SCPI communication.
    """

    db = get_database()  # Get global requirements database

    # Power supply isolation tests link to REQ-001 and REQ-002
    db.link_test("REQ-001", "test_power_not_in_state_b")  # PSU off in state B
    db.link_test("REQ-002", "test_psu_voltage_configuration")  # Voltage limits


def link_phase_2_tests() -> None:
    """Link Phase 2 tests to requirements.

    Phase 2 validates SimulatedCharger OCPP and state machine implementation.
    """

    db = get_database()  # Get global requirements database

    # Happy path test covers multiple requirements
    db.link_test("REQ-004", "test_charging_session_happy_path")  # OCPP boot
    db.link_test("REQ-005", "test_charging_session_happy_path")  # Authorization
    db.link_test("REQ-006", "test_charging_session_happy_path")  # Transaction lifecycle
    db.link_test("REQ-008", "test_charging_session_happy_path")  # State C after auth

    # OCPP message sequence test
    db.link_test("REQ-009", "test_ocpp_message_sequence")  # OCPP 1.6J format

    # State machine test
    db.link_test("REQ-003", "test_state_transitions")  # IEC 61851 enforcement
    db.link_test("REQ-010", "test_state_transitions")  # IEC 61851 state machine

    # Authorization test
    db.link_test("REQ-005", "test_cannot_start_transaction_without_auth")  # Auth required

    # Power in wrong state test
    db.link_test("REQ-001", "test_power_not_in_state_b")  # PSU off in state B

    # Multiple transactions test
    db.link_test("REQ-006", "test_multiple_transactions")  # Transaction lifecycle
    db.link_test("REQ-007", "test_multiple_transactions")  # Unique transaction IDs
    db.link_test("REQ-011", "test_multiple_transactions")  # Multiple transactions

    # Stop transaction twice test
    db.link_test("REQ-006", "test_cannot_stop_twice")  # Transaction lifecycle

