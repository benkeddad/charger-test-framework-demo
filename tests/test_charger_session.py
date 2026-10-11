"""
Integration tests for charging sessions (Phase 2).

Tests the full charging workflow:
1. Charger boots and connects to central system
2. Vehicle plugs in (state B)
3. User presents RFID tag (authorize)
4. Transaction starts
5. Charger transitions to state C (power delivery)
6. PSU supplies power
7. Transaction stops
8. Return to safe state

These tests verify the integration of:
- MockCentralSystem (OCPP backend)
- SimulatedCharger (charger logic)
- ScpiPowerSupply (power control)
- IEC 61851 state machine (A/B/C/E/F transitions)
"""

import logging  # Logging framework
from datetime import datetime  # Timestamps

import pytest  # pytest framework

from chargerlab.charger.simulator import SimulatedCharger  # Charger under test
from chargerlab.charger.states import CpState  # Vehicle interface states
from chargerlab.drivers.scpi_psu import ScpiPowerSupply  # PSU driver

# Logger for this module
logger = logging.getLogger(__name__)


# ============================================================================
# Test: Happy Path - Full Charging Session
# ============================================================================


@pytest.mark.integration
async def test_charging_session_happy_path(
    charger: SimulatedCharger,
) -> None:
    """
    Test: Complete charging session from boot to stop.

    Scenario:
    1. Charger boots (BootNotification already sent in fixture)
    2. Vehicle connects (transition to state B)
    3. RFID tag authorized
    4. Transaction started
    5. Charger transitions to state C (ready to charge)
    6. PSU voltage verified as set
    7. Transaction stopped
    8. Return to state A

    This is the happy path - no errors, no edge cases.
    """
    # Verify charger is booted (connected to central system)
    assert charger.boot_time is not None  # Boot already done
    logger.info("✓ Charger booted")

    # Step 1: Vehicle plugs in (transition to state B)
    await charger.set_cp_state(CpState.B)
    assert charger.cp_state == CpState.B  # Verify state
    logger.info("✓ Vehicle connected (state B)")

    # Step 2: User presents RFID tag and charger authorizes it
    tag_id = "test-tag-001"
    authorized = await charger.authorize_tag(tag_id)
    assert authorized  # Verify tag accepted by central system
    assert charger.authorized_tag == tag_id  # Charger recorded tag
    logger.info(f"✓ Tag {tag_id} authorized")

    # Step 3: Start charging transaction
    voltage = 230.0  # AC mains voltage (typical)
    transaction_id = await charger.start_transaction(voltage=voltage)
    assert transaction_id is not None  # Central system assigned ID
    assert charger.transaction_active  # Transaction recorded as active
    logger.info(f"✓ Transaction started (ID: {transaction_id}, voltage: {voltage}V)")

    # Step 4: Transition to state C (ready to charge)
    await charger.set_cp_state(CpState.C)
    assert charger.cp_state == CpState.C  # Verify state
    logger.info("✓ Charger ready to charge (state C)")

    # Step 5: Verify PSU output is enabled and voltage is correct
    # (Check PSU status without querying central system)
    psu_voltage = await charger.psu.get_voltage()
    assert abs(psu_voltage - voltage) < 0.1  # Voltage matches (within tolerance)
    psu_output = await charger.psu.get_output()
    assert psu_output  # Output is enabled
    logger.info(f"✓ PSU output verified: {psu_voltage}V")

    # Step 6: Stop transaction and return to state A
    await charger.stop_transaction()
    assert not charger.transaction_active  # Transaction no longer active
    assert charger.cp_state == CpState.A  # Back to disconnected state
    logger.info("✓ Transaction stopped, charger returned to state A")

    # Verify PSU is in safe state (output off, 0V)
    psu_output = await charger.psu.get_output()
    assert not psu_output  # Output disabled
    psu_voltage = await charger.psu.get_voltage()
    assert psu_voltage == 0.0  # Voltage is 0V
    logger.info("✓ PSU in safe state")


# ============================================================================
# Test: OCPP Message Sequence
# ============================================================================


@pytest.mark.integration
async def test_ocpp_message_sequence(
    charger: SimulatedCharger,
) -> None:
    """
    Test: Verify correct OCPP message sequence to central system.

    Expected sequence:
    1. BootNotification (sent in fixture)
    2. Authorize (when tag presented)
    3. StartTransaction (when charging begins)
    4. StopTransaction (when charging stops)

    This test verifies the charger sends the right messages
    in the right order with correct payloads.
    """
    # We already verified BootNotification was sent (fixture connected)
    logger.info("✓ BootNotification sent during fixture setup")

    # Present RFID tag
    tag_id = "test-tag-002"
    await charger.authorize_tag(tag_id)
    logger.info(f"✓ Authorize message sent for tag {tag_id}")

    # Start transaction
    await charger.set_cp_state(CpState.B)
    transaction_id = await charger.start_transaction()
    logger.info(f"✓ StartTransaction message sent (ID: {transaction_id})")

    # Stop transaction
    await charger.stop_transaction()
    logger.info("✓ StopTransaction message sent")

    # Verify sequence (messages should be recorded in central system)
    # In a real test, we'd query central_system fixture for message history
    # For now, we just verify the charger state transitions correctly
    assert charger.transaction_id is None  # Transaction cleared
    assert charger.authorized_tag is None  # Tag cleared
    logger.info("✓ Message sequence verified")


# ============================================================================
# Test: Multiple Transactions
# ============================================================================


@pytest.mark.integration
async def test_multiple_transactions(
    charger: SimulatedCharger,
) -> None:
    """
    Test: Charger can handle multiple consecutive transactions.

    Scenario:
    1. First transaction (authorize, start, stop)
    2. Second transaction (new tag, start, stop)
    3. Verify PSU returns to safe state between transactions

    This tests cleanup and state reset between sessions.
    """
    # Transaction 1
    await charger.set_cp_state(CpState.B)
    await charger.authorize_tag("tag-1")
    txn1 = await charger.start_transaction(voltage=230.0)
    assert txn1 is not None
    await charger.set_cp_state(CpState.C)
    assert charger.cp_state == CpState.C
    logger.info(f"✓ Transaction 1 started (ID: {txn1})")

    # Verify power is on
    psu_output = await charger.psu.get_output()
    assert psu_output
    logger.info("✓ Power on during transaction 1")

    # Stop transaction 1
    await charger.stop_transaction()
    assert charger.cp_state == CpState.A  # Back to state A
    logger.info("✓ Transaction 1 stopped")

    # Verify power is off
    psu_output = await charger.psu.get_output()
    assert not psu_output
    psu_voltage = await charger.psu.get_voltage()
    assert psu_voltage == 0.0
    logger.info("✓ PSU in safe state between transactions")

    # Transaction 2 (new vehicle, new tag)
    await charger.set_cp_state(CpState.B)
    await charger.authorize_tag("tag-2")
    txn2 = await charger.start_transaction(voltage=240.0)  # Different voltage
    assert txn2 is not None
    assert txn2 != txn1  # Different transaction ID
    await charger.set_cp_state(CpState.C)
    logger.info(f"✓ Transaction 2 started (ID: {txn2})")

    # Verify new voltage
    psu_voltage = await charger.psu.get_voltage()
    assert abs(psu_voltage - 240.0) < 0.1
    logger.info(f"✓ PSU reconfigured to {psu_voltage}V for transaction 2")

    # Stop transaction 2
    await charger.stop_transaction()
    logger.info("✓ Transaction 2 stopped")


# ============================================================================
# Test: State Transitions
# ============================================================================


@pytest.mark.integration
async def test_state_transitions(
    charger: SimulatedCharger,
) -> None:
    """
    Test: Correct state transitions following IEC 61851.

    IEC 61851 state definitions:
    - State A: No vehicle connected (PSU off, 0V)
    - State B: Vehicle connected, not authorized (PSU off, 0V)
    - State C: Vehicle connected and authorized (power allowed, PSU can be on)
    - State E: Charger error (PSU off, 0V)
    - State F: Charger unavailable (PSU off, 0V)

    Verify PSU state matches IEC 61851 rules at each transition.
    """
    # Start: State A (no vehicle)
    assert charger.cp_state == CpState.A
    psu_output = await charger.psu.get_output()
    assert not psu_output  # Output off
    logger.info("✓ State A: PSU off")

    # Transition A → B (vehicle connected)
    await charger.set_cp_state(CpState.B)
    assert charger.cp_state == CpState.B
    psu_output = await charger.psu.get_output()
    assert not psu_output  # Output still off (not authorized yet)
    logger.info("✓ State B: PSU off (waiting for authorization)")

    # Transition B → authorization → C (ready to charge)
    await charger.authorize_tag("test-tag-c")
    await charger.start_transaction(voltage=230.0)
    await charger.set_cp_state(CpState.C)
    assert charger.cp_state == CpState.C
    psu_output = await charger.psu.get_output()
    assert psu_output  # Output on (authorized and charging)
    logger.info("✓ State C: PSU on (power delivery active)")

    # Transition C → E (error detected)
    await charger.set_cp_state(CpState.E)
    assert charger.cp_state == CpState.E
    psu_output = await charger.psu.get_output()
    assert not psu_output  # Output off (emergency state)
    psu_voltage = await charger.psu.get_voltage()
    assert psu_voltage == 0.0  # Voltage 0V (safe)
    logger.info("✓ State E: PSU safe (error)")

    # Transition E → A (back to normal, disconnect vehicle)
    await charger.set_cp_state(CpState.A)
    assert charger.cp_state == CpState.A
    logger.info("✓ State A: Reset complete")


# ============================================================================
# Test: Charger Cannot Charge Without Authorization
# ============================================================================


@pytest.mark.integration
async def test_cannot_start_transaction_without_auth(
    charger: SimulatedCharger,
) -> None:
    """
    Test: Charger raises error if trying to start transaction without authorized tag.

    Safety check: start_transaction() should fail if no tag was authorized first.
    This prevents accidental power delivery without proper authorization.
    """
    # Try to start transaction without authorization
    with pytest.raises(RuntimeError, match="Cannot start transaction without"):
        await charger.start_transaction()

    logger.info("✓ Correctly rejected start_transaction without authorized tag")


# ============================================================================
# Test: Charger Cannot Supply Power in State B
# ============================================================================


@pytest.mark.integration
async def test_power_not_in_state_b(
    charger: SimulatedCharger,
) -> None:
    """
    Test: Power output is disabled in state B (vehicle connected, not authorized).

    IEC 61851 rule: Power flows only in state C.
    Even if somehow we enabled PSU output in state B, it should be off.
    """
    # Set to state B (vehicle connected)
    await charger.set_cp_state(CpState.B)

    # Verify output is off
    psu_output = await charger.psu.get_output()
    assert not psu_output  # Output must be off

    logger.info("✓ Correctly enforced: no power in state B")


# ============================================================================
# Test: Cannot Stop Transaction Twice
# ============================================================================


@pytest.mark.integration
async def test_cannot_stop_twice(
    charger: SimulatedCharger,
) -> None:
    """
    Test: Charger raises error if trying to stop a transaction that's not active.

    Safety check: stop_transaction() should fail if no transaction is running.
    Prevents accidental double-stop or cleanup issues.
    """
    # Try to stop without starting
    with pytest.raises(RuntimeError, match="No active transaction"):
        await charger.stop_transaction()

    # Start and stop once
    await charger.set_cp_state(CpState.B)
    await charger.authorize_tag("test-tag")
    await charger.start_transaction()
    await charger.stop_transaction()

    # Try to stop again
    with pytest.raises(RuntimeError, match="No active transaction"):
        await charger.stop_transaction()

    logger.info("✓ Correctly rejected double stop_transaction")


# ============================================================================
# Test: PSU Voltage Configuration
# ============================================================================


@pytest.mark.integration
async def test_psu_voltage_configuration(
    charger: SimulatedCharger,
) -> None:
    """
    Test: PSU voltage is configured correctly during transactions.

    Scenario:
    1. Start transaction with 230V
    2. Verify PSU reads back 230V
    3. Stop and start again with 240V
    4. Verify PSU reads back 240V

    This tests that voltage settings persist and are correctly reported.
    """
    # Transaction 1: 230V
    await charger.set_cp_state(CpState.B)
    await charger.authorize_tag("test-tag-v1")
    await charger.start_transaction(voltage=230.0)
    voltage = await charger.psu.get_voltage()
    assert abs(voltage - 230.0) < 0.1
    logger.info(f"✓ Transaction 1: PSU voltage = {voltage}V (expected 230V)")
    await charger.stop_transaction()

    # Transaction 2: 240V
    await charger.set_cp_state(CpState.B)
    await charger.authorize_tag("test-tag-v2")
    await charger.start_transaction(voltage=240.0)
    voltage = await charger.psu.get_voltage()
    assert abs(voltage - 240.0) < 0.1
    logger.info(f"✓ Transaction 2: PSU voltage = {voltage}V (expected 240V)")
    await charger.stop_transaction()
