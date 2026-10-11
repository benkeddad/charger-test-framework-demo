"""Phase 5: OCPP Charger Core Functionality Tests

Tests for core OCPP protocol conformance and charger behavior:
- CHARGER-001: Valid OCPP connection acceptance
- CHARGER-002: Malformed message rejection
- CHARGER-003: Power supply state changes
- CHARGER-004: IEC 61851 state machine enforcement
- CHARGER-005: Overcurrent condition detection

These tests validate that the simulated charger properly implements
the protocol and safety features required for realistic test scenarios.
"""

import pytest  # Test framework
import asyncio  # Async support for OCPP protocol
from unittest.mock import Mock, AsyncMock, patch  # Mocking for unit tests

from chargerlab.requirements.pytest_plugin import requires  # Requirement decorator
from chargerlab.equipment.simulated_charger import SimulatedCharger  # Charger under test


class TestChargerOCPPConnection:
    """Test CHARGER-001: Simulated charger accepts valid OCPP connections."""

    @requires("CHARGER-001", "INFRA-001")  # Valid connection, must be deterministic
    async def test_charger_accepts_valid_ocpp_connection(self):
        """Charger should accept a valid OCPP 1.6 connection from central system."""
        # Create charger instance with simulated endpoint
        charger = SimulatedCharger(charger_id="TEST-001", endpoint="ws://127.0.0.1:9000")
        
        # Mock central system connection
        mock_central = AsyncMock()  # Mock remote central system
        
        try:
            # Attempt to establish OCPP connection (should not raise)
            connection = await charger.connect_to_central(mock_central)
            
            # Verify connection is established
            assert connection is not None  # Connection object returned
            assert connection.connected  # Connection state is active
            assert connection.charger_id == "TEST-001"  # ID properly propagated
        finally:
            # Clean up resources
            await charger.disconnect()

    @requires("CHARGER-001", "INFRA-001")  # Connection validation, deterministic
    async def test_charger_connection_includes_required_metadata(self):
        """Charger should send required metadata during OCPP handshake."""
        # Create charger with test configuration
        charger = SimulatedCharger(charger_id="UNIT-TEST", model="SIM-V1")
        
        # Track handshake metadata sent by charger
        handshake_data = {}
        
        # Mock central system to capture connection data
        async def capture_handshake(metadata):  # Receive charger metadata
            nonlocal handshake_data  # Update outer scope
            handshake_data = metadata  # Store captured data
        
        # Connect with capture handler
        mock_central = AsyncMock(receive_handshake=capture_handshake)
        connection = await charger.connect_to_central(mock_central)
        
        # Verify all required metadata was sent
        assert handshake_data.get("charger_id") == "UNIT-TEST"  # ID included
        assert handshake_data.get("model") == "SIM-V1"  # Model included
        assert "firmware_version" in handshake_data  # Version included
        
        # Cleanup
        await charger.disconnect()

    @requires("CHARGER-001", "INFRA-001")  # Connection timeout handling, deterministic
    async def test_charger_connection_timeout_handling(self):
        """Charger should properly handle connection timeouts."""
        # Create charger instance
        charger = SimulatedCharger(charger_id="TIMEOUT-TEST")
        
        # Mock central system that times out
        mock_central = AsyncMock()  # Unresponsive central
        mock_central.connect.side_effect = asyncio.TimeoutError()  # Simulate timeout
        
        # Connection attempt should timeout gracefully
        with pytest.raises(asyncio.TimeoutError):  # Timeout expected
            await charger.connect_to_central(mock_central, timeout=0.1)  # Very short timeout


class TestChargerMalformedMessages:
    """Test CHARGER-002: Charger rejects malformed OCPP messages."""

    @requires("CHARGER-002", "INFRA-001")  # Malformed rejection, deterministic
    async def test_charger_rejects_invalid_message_structure(self):
        """Charger should reject messages with invalid OCPP structure."""
        # Create connected charger
        charger = SimulatedCharger(charger_id="MALFORMED-TEST")
        mock_central = AsyncMock()
        await charger.connect_to_central(mock_central)
        
        try:
            # Send message with invalid structure (missing message type)
            invalid_message = ["InvalidMessage", 123]  # Only 2 fields, needs 3+
            
            # Charger should reject and not process
            with pytest.raises(ValueError):  # Invalid format raises error
                await charger.receive_message(invalid_message)
        finally:
            await charger.disconnect()

    @requires("CHARGER-002", "INFRA-001")  # Invalid field handling, deterministic
    async def test_charger_rejects_invalid_field_types(self):
        """Charger should reject messages with invalid field types."""
        # Create connected charger
        charger = SimulatedCharger(charger_id="FIELD-TYPE-TEST")
        mock_central = AsyncMock()
        await charger.connect_to_central(mock_central)
        
        try:
            # Send message with wrong field types (string where int expected)
            invalid_message = {
                "message_type": "AUTHORIZE",  # Valid type
                "call_id": "not_a_number",  # Should be integer
                "action": "Authorize"
            }
            
            # Charger should reject invalid types
            with pytest.raises((TypeError, ValueError)):  # Type mismatch error
                await charger.receive_message(invalid_message)
        finally:
            await charger.disconnect()

    @requires("CHARGER-002", "INFRA-001")  # Malformed recovery, deterministic
    async def test_charger_continues_after_malformed_message(self):
        """Charger should remain operational after rejecting malformed message."""
        # Create connected charger
        charger = SimulatedCharger(charger_id="RECOVERY-TEST")
        mock_central = AsyncMock()
        await charger.connect_to_central(mock_central)
        
        try:
            # Send malformed message
            try:
                invalid = ["BadMessage"]  # Invalid structure
                await charger.receive_message(invalid)
            except ValueError:
                pass  # Expected rejection
            
            # Send valid message after malformed (should work)
            valid_message = {
                "message_type": "HEARTBEAT",
                "call_id": 42,
                "action": "Heartbeat"
            }
            
            # Should process valid message without error
            response = await charger.receive_message(valid_message)
            assert response is not None  # Got valid response
            assert response.get("status") == "OK"  # Response indicates success
        finally:
            await charger.disconnect()


class TestChargerPowerSupplyStateChanges:
    """Test CHARGER-003: Charger handles power supply state changes gracefully."""

    @requires("CHARGER-003", "INFRA-001")  # Power transitions, deterministic
    async def test_charger_handles_power_supply_available_transition(self):
        """Charger should handle power supply becoming available."""
        # Create charger without power initially
        charger = SimulatedCharger(charger_id="POWER-AVAIL-TEST", power_available=False)
        
        # Power supply comes online
        charger.power_supply.set_state(available=True)  # Power now available
        
        # Charger should process transition without crashing
        state = await charger.get_state()  # Query charger state
        assert state.power_available is True  # Power reflected in state
        assert state.operational is True  # Charger operational

    @requires("CHARGER-003", "INFRA-001")  # Power loss handling, deterministic
    async def test_charger_handles_power_supply_loss(self):
        """Charger should handle power supply loss gracefully."""
        # Create charger with active charging session
        charger = SimulatedCharger(charger_id="POWER-LOSS-TEST", power_available=True)
        mock_central = AsyncMock()
        await charger.connect_to_central(mock_central)
        
        try:
            # Start charging session
            session = await charger.start_charging_session("vehicle-123")
            assert session.active is True  # Session active
            
            # Power supply fails
            charger.power_supply.set_state(available=False)  # Simulate power loss
            
            # Charger should continue running (not crash)
            state = await charger.get_state()  # Query state
            assert state.operational is True  # Still operational
            assert state.power_available is False  # Power loss recorded
            
            # Session should be paused/stopped
            assert session.active is False  # Session stopped due to power loss
        finally:
            await charger.disconnect()

    @requires("CHARGER-003", "INFRA-001")  # Power restoration, deterministic
    async def test_charger_recovers_from_power_restoration(self):
        """Charger should recover when power is restored."""
        # Create charger, lose power, then restore
        charger = SimulatedCharger(charger_id="POWER-RESTORE-TEST")
        
        # Start with power
        charger.power_supply.set_state(available=True)
        initial_state = await charger.get_state()
        assert initial_state.power_available is True
        
        # Lose power
        charger.power_supply.set_state(available=False)
        lost_power_state = await charger.get_state()
        assert lost_power_state.power_available is False
        
        # Restore power
        charger.power_supply.set_state(available=True)
        restored_state = await charger.get_state()
        
        # Verify recovery
        assert restored_state.power_available is True  # Power restored
        assert restored_state.operational is True  # Operational again


class TestChargerStateTransitions:
    """Test CHARGER-004: Charger enforces IEC 61851 state machine correctly."""

    @requires("CHARGER-004", "INFRA-001")  # State machine, deterministic
    async def test_charger_state_machine_valid_transition(self):
        """Charger should allow valid IEC 61851 state transitions."""
        # Create charger in initial state (A: not connected)
        charger = SimulatedCharger(charger_id="STATE-VALID-TEST")
        
        # Verify initial state
        state = await charger.get_state()
        assert state.iec_61851_state == "A"  # Initial: not connected
        
        # Transition to B (connected, no charging authorized)
        charger.plug_in_vehicle()  # Simulate vehicle connection
        state = await charger.get_state()
        assert state.iec_61851_state == "B"  # Valid transition A→B
        
        # Transition to C (connected, charging authorized)
        await charger.authorize_charging("vehicle-123")
        state = await charger.get_state()
        assert state.iec_61851_state == "C"  # Valid transition B→C

    @requires("CHARGER-004", "INFRA-001")  # Invalid transitions, deterministic
    async def test_charger_rejects_invalid_state_transition(self):
        """Charger should reject invalid state transitions."""
        # Create charger
        charger = SimulatedCharger(charger_id="STATE-INVALID-TEST")
        
        # Charger starts in state A (not connected)
        state = await charger.get_state()
        assert state.iec_61851_state == "A"
        
        # Try invalid transition: A → C (skip B)
        # Should not be allowed (must go A → B first)
        with pytest.raises(ValueError):  # Invalid transition
            await charger.force_state("C")  # Try to force invalid state

    @requires("CHARGER-004", "INFRA-001")  # State consistency, deterministic
    async def test_charger_maintains_state_consistency(self):
        """Charger should maintain consistent state during transitions."""
        # Create charger and perform multiple transitions
        charger = SimulatedCharger(charger_id="STATE-CONSISTENCY-TEST")
        
        # Sequence of valid transitions
        transitions = [
            ("A", lambda: None),  # Initial state
            ("B", lambda: charger.plug_in_vehicle()),  # Connect vehicle
            ("C", lambda: charger.authorize_charging("v123")),  # Authorize
        ]
        
        for expected_state, action in transitions:
            # Perform action (if any)
            if action:
                await action()  # Execute transition action
            
            # Verify state
            state = await charger.get_state()
            assert state.iec_61851_state == expected_state  # Expected state reached


class TestChargerOvercurrentDetection:
    """Test CHARGER-005: Charger detects and reports overcurrent conditions."""

    @requires("CHARGER-005", "INFRA-001")  # Overcurrent detection, deterministic
    async def test_charger_detects_overcurrent(self):
        """Charger should detect when current exceeds safe limits."""
        # Create charger with current monitoring
        charger = SimulatedCharger(charger_id="OVERCURRENT-TEST", max_current=16.0)
        
        # Simulate charging session
        session = await charger.start_charging_session("vehicle-123")
        assert session.active is True
        
        # Gradually increase current (normal behavior)
        await charger.set_charging_current(10.0)  # Normal current
        assert not charger.overcurrent_detected  # No fault
        
        # Exceed safe limit
        await charger.set_charging_current(25.0)  # Exceeds max (16A)
        
        # Overcurrent should be detected
        assert charger.overcurrent_detected is True  # Fault detected
        fault = charger.get_last_fault()
        assert fault.fault_type == "OVERCURRENT"  # Correct fault type
        assert fault.current_amps == 25.0  # Fault parameters recorded

    @requires("CHARGER-005", "INFRA-001")  # Safety shutdown, deterministic
    async def test_charger_shuts_down_charging_on_overcurrent(self):
        """Charger should immediately stop charging on overcurrent."""
        # Create charger
        charger = SimulatedCharger(charger_id="OVERCURRENT-SHUTDOWN-TEST", max_current=16.0)
        
        # Start active charging session
        session = await charger.start_charging_session("vehicle-123")
        assert session.active is True
        assert charger.is_charging() is True
        
        # Trigger overcurrent condition
        await charger.set_charging_current(30.0)  # Way over limit
        
        # Verify charging stopped
        assert charger.is_charging() is False  # Charging stopped
        assert charger.overcurrent_detected is True  # Fault recorded
        
        # Session should be stopped
        assert session.active is False  # Session terminated

    @requires("CHARGER-005", "INFRA-001")  # Recovery capability, deterministic
    async def test_charger_can_recover_after_overcurrent_reset(self):
        """Charger should allow normal operation after overcurrent reset."""
        # Create charger
        charger = SimulatedCharger(charger_id="OVERCURRENT-RECOVERY-TEST", max_current=16.0)
        
        # Trigger overcurrent
        await charger.set_charging_current(25.0)
        assert charger.overcurrent_detected is True
        
        # Reset overcurrent protection
        charger.reset_overcurrent_fault()  # Clear fault
        assert charger.overcurrent_detected is False
        
        # Should be able to charge normally again
        session = await charger.start_charging_session("vehicle-456")
        assert session.active is True
        
        # Normal current should work
        await charger.set_charging_current(12.0)  # Normal
        assert charger.overcurrent_detected is False  # No fault
        assert charger.is_charging() is True  # Charging active
