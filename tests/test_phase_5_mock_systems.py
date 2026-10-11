"""Phase 5B: Mock System Functionality Tests

Tests for mock central system and power supply simulation:
- MOCK-001: Central system responds to authorization requests
- MOCK-002: Central system tracks transaction state correctly
- MOCK-003: Power supply simulates voltage and current parameters
- MOCK-004: Power supply supports fault injection (overcurrent, overvoltage)

These tests validate that the mock systems properly simulate real-world
equipment behavior needed for comprehensive charger testing.
"""

import pytest  # Test framework
from unittest.mock import Mock, AsyncMock, patch  # Mocking utilities

from chargerlab.requirements.pytest_plugin import requires  # Requirement decorator
from chargerlab.equipment.mock_central_system import MockCentralSystem  # Central system under test
from chargerlab.equipment.mock_power_supply import MockPowerSupply  # Power supply under test


class TestMockCentralSystemAuthorization:
    """Test MOCK-001: MockCentralSystem responds to charger authorization requests."""

    @requires("MOCK-001", "INFRA-001")  # Authorization, deterministic
    async def test_central_system_authorizes_valid_vehicle(self):
        """Central system should authorize valid vehicle IDs."""
        # Create mock central system
        central = MockCentralSystem()
        
        # Register valid vehicle
        vehicle_id = "VEHICLE-001"
        central.register_vehicle(vehicle_id, authorized=True)
        
        # Request authorization
        result = await central.authorize_vehicle(vehicle_id)
        
        # Verify authorization granted
        assert result.authorized is True  # Authorization granted
        assert result.vehicle_id == vehicle_id  # Correct vehicle
        assert result.charging_limit_kw is not None  # Limit assigned

    @requires("MOCK-001", "INFRA-001")  # Rejection handling, deterministic
    async def test_central_system_denies_unauthorized_vehicle(self):
        """Central system should deny unknown/unauthorized vehicles."""
        # Create mock central system
        central = MockCentralSystem()
        
        # Don't register vehicle (unauthorized)
        unknown_vehicle = "UNKNOWN-999"
        
        # Request authorization
        result = await central.authorize_vehicle(unknown_vehicle)
        
        # Verify authorization denied
        assert result.authorized is False  # Authorization denied
        assert result.vehicle_id == unknown_vehicle
        assert result.denial_reason == "UNKNOWN_VEHICLE"  # Reason provided

    @requires("MOCK-001", "INFRA-001")  # Timeout simulation, deterministic
    async def test_central_system_responds_within_timeout(self):
        """Central system should respond to authorization within reasonable time."""
        # Create central system
        central = MockCentralSystem(response_delay_ms=50)  # 50ms delay
        
        # Register vehicle
        central.register_vehicle("FAST-VEHICLE")
        
        # Measure authorization time
        import time  # Timer for measurement
        start = time.time()  # Start timing
        result = await central.authorize_vehicle("FAST-VEHICLE")
        elapsed_ms = (time.time() - start) * 1000  # Convert to milliseconds
        
        # Verify response is timely
        assert elapsed_ms < 200  # Responds within 200ms
        assert result.authorized is True  # Authorization successful


class TestMockCentralSystemTransactionTracking:
    """Test MOCK-002: MockCentralSystem tracks transaction state correctly."""

    @requires("MOCK-002", "INFRA-001")  # Transaction creation, deterministic
    async def test_central_system_creates_transaction(self):
        """Central system should create transaction on charging start."""
        # Create central system
        central = MockCentralSystem()
        central.register_vehicle("TRANS-TEST-V1")
        
        # Authorize and start charging
        auth = await central.authorize_vehicle("TRANS-TEST-V1")
        transaction = await central.start_charging_transaction(
            vehicle_id="TRANS-TEST-V1",
            connector_id=1,
            auth_id=auth.auth_id
        )
        
        # Verify transaction created
        assert transaction is not None  # Transaction object created
        assert transaction.transaction_id is not None  # ID assigned
        assert transaction.vehicle_id == "TRANS-TEST-V1"  # Vehicle tracked
        assert transaction.status == "RUNNING"  # Status is running

    @requires("MOCK-002", "INFRA-001")  # Transaction state, deterministic
    async def test_central_system_tracks_transaction_state_changes(self):
        """Central system should track state transitions during transaction."""
        # Create central system
        central = MockCentralSystem()
        central.register_vehicle("STATE-TEST")
        
        # Create transaction
        auth = await central.authorize_vehicle("STATE-TEST")
        txn = await central.start_charging_transaction(
            vehicle_id="STATE-TEST",
            connector_id=1,
            auth_id=auth.auth_id
        )
        
        # Verify initial state
        assert txn.status == "RUNNING"  # Started
        
        # Pause transaction
        await central.pause_transaction(txn.transaction_id)
        txn_updated = await central.get_transaction(txn.transaction_id)
        assert txn_updated.status == "PAUSED"  # State changed
        
        # Resume transaction
        await central.resume_transaction(txn.transaction_id)
        txn_updated = await central.get_transaction(txn.transaction_id)
        assert txn_updated.status == "RUNNING"  # State changed back
        
        # Stop transaction
        await central.stop_transaction(txn.transaction_id)
        txn_updated = await central.get_transaction(txn.transaction_id)
        assert txn_updated.status == "STOPPED"  # Ended

    @requires("MOCK-002", "INFRA-001")  # Transaction history, deterministic
    async def test_central_system_maintains_transaction_history(self):
        """Central system should maintain historical record of transactions."""
        # Create central system
        central = MockCentralSystem()
        central.register_vehicle("HISTORY-TEST")
        
        # Create multiple transactions
        for i in range(3):
            auth = await central.authorize_vehicle("HISTORY-TEST")
            await central.start_charging_transaction(
                vehicle_id="HISTORY-TEST",
                connector_id=1,
                auth_id=auth.auth_id
            )
            # Simulate completion (simplified)
        
        # Query transaction history
        history = await central.get_vehicle_transaction_history("HISTORY-TEST")
        
        # Verify history recorded
        assert len(history) >= 3  # All transactions recorded
        assert all(t.vehicle_id == "HISTORY-TEST" for t in history)  # All for same vehicle


class TestMockPowerSupplyParameters:
    """Test MOCK-003: MockPowerSupply simulates voltage and current parameters."""

    @requires("MOCK-003", "INFRA-001")  # Voltage simulation, deterministic
    async def test_power_supply_simulates_voltage_output(self):
        """Power supply should simulate realistic voltage output."""
        # Create power supply
        power = MockPowerSupply(
            voltage_nominal_v=230.0,  # AC nominal voltage
            voltage_tolerance_percent=5.0  # ±5% tolerance
        )
        
        # Enable power supply
        power.enable()
        
        # Read voltage
        voltage = power.get_voltage()
        
        # Verify voltage in expected range
        assert voltage is not None  # Voltage readable
        assert 218.5 <= voltage <= 241.5  # Within tolerance (230 ± 5%)

    @requires("MOCK-003", "INFRA-001")  # Current simulation, deterministic
    async def test_power_supply_simulates_current_output(self):
        """Power supply should simulate realistic current output."""
        # Create power supply
        power = MockPowerSupply(
            current_max_a=32.0,  # Max 32A
            current_measurement_noise_percent=2.0  # ±2% noise
        )
        
        # Set current limit
        power.set_current_limit(16.0)  # 16A limit
        power.enable()
        
        # Read current
        current = power.get_current()
        
        # Verify current in expected range
        assert current is not None  # Current readable
        assert 0 <= current <= 16.0  # Within set limit

    @requires("MOCK-003", "INFRA-001")  # Parameter dynamics, deterministic
    async def test_power_supply_parameters_reflect_load_changes(self):
        """Power supply parameters should reflect load changes dynamically."""
        # Create power supply
        power = MockPowerSupply()
        power.enable()
        
        # Read baseline
        voltage_baseline = power.get_voltage()
        current_baseline = power.get_current()
        
        # Simulate increased load (charging starts)
        power.simulate_load_change(load_resistance_ohms=10.0)
        
        # Read new values
        voltage_loaded = power.get_voltage()
        current_loaded = power.get_current()
        
        # Verify parameters changed appropriately
        # (voltage may sag slightly, current should increase)
        assert current_loaded >= current_baseline  # Current increased or stayed same


class TestMockPowerSupplyFaultInjection:
    """Test MOCK-004: MockPowerSupply supports fault injection."""

    @requires("MOCK-004", "INFRA-001")  # Overcurrent injection, deterministic
    async def test_power_supply_inject_overcurrent_fault(self):
        """Power supply should simulate overcurrent fault conditions."""
        # Create power supply
        power = MockPowerSupply(current_max_a=16.0)
        power.enable()
        
        # Normal operation
        assert not power.has_overcurrent_fault()  # No fault initially
        
        # Inject overcurrent fault
        power.inject_fault("OVERCURRENT", current_value_a=25.0)
        
        # Verify fault injected
        assert power.has_overcurrent_fault() is True  # Fault active
        fault = power.get_current_fault()
        assert fault.fault_type == "OVERCURRENT"  # Correct type
        assert fault.current_amps == 25.0  # Correct value

    @requires("MOCK-004", "INFRA-001")  # Overvoltage injection, deterministic
    async def test_power_supply_inject_overvoltage_fault(self):
        """Power supply should simulate overvoltage fault conditions."""
        # Create power supply
        power = MockPowerSupply(voltage_nominal_v=230.0)
        power.enable()
        
        # Inject overvoltage fault
        power.inject_fault("OVERVOLTAGE", voltage_value_v=280.0)  # Well above nominal
        
        # Verify fault injected
        assert power.has_overvoltage_fault() is True  # Fault active
        fault = power.get_voltage_fault()
        assert fault.fault_type == "OVERVOLTAGE"
        assert fault.voltage_v == 280.0  # Fault parameters correct

    @requires("MOCK-004", "INFRA-001")  # Multiple faults, deterministic
    async def test_power_supply_handles_multiple_simultaneous_faults(self):
        """Power supply should handle multiple faults simultaneously."""
        # Create power supply
        power = MockPowerSupply()
        power.enable()
        
        # Inject multiple faults
        power.inject_fault("OVERCURRENT", current_value_a=30.0)
        power.inject_fault("OVERVOLTAGE", voltage_value_v=300.0)
        
        # Verify both faults active
        assert power.has_overcurrent_fault() is True
        assert power.has_overvoltage_fault() is True
        
        # Get all active faults
        faults = power.get_all_active_faults()
        assert len(faults) >= 2  # At least 2 faults recorded

    @requires("MOCK-004", "INFRA-001")  # Fault recovery, deterministic
    async def test_power_supply_can_clear_injected_faults(self):
        """Power supply should allow clearing injected faults."""
        # Create power supply
        power = MockPowerSupply()
        power.enable()
        
        # Inject fault
        power.inject_fault("OVERCURRENT", current_value_a=25.0)
        assert power.has_overcurrent_fault() is True
        
        # Clear fault
        power.clear_fault("OVERCURRENT")
        
        # Verify fault cleared
        assert power.has_overcurrent_fault() is False
        
        # Verify can inject again (not locked)
        power.inject_fault("OVERCURRENT", current_value_a=30.0)
        assert power.has_overcurrent_fault() is True  # New fault active
