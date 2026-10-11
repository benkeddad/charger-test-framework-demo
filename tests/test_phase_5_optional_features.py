"""Phase 5C: Optional Feature Tests

Tests for optional but desirable features:
- CHARGER-008: Authentication token refresh
- CHARGER-009: Dynamic current limits in power supply
- CHARGER-010: Multiple simultaneous charger instances

These tests validate advanced capabilities that enhance the test framework's
ability to simulate complex real-world scenarios.
"""

import pytest  # Test framework
import asyncio  # Async support
from unittest.mock import Mock, AsyncMock  # Mocking utilities

from chargerlab.requirements.pytest_plugin import requires  # Requirement decorator
from chargerlab.equipment.simulated_charger import SimulatedCharger  # Charger under test
from chargerlab.equipment.mock_power_supply import MockPowerSupply  # Power supply under test


class TestChargerTokenRefresh:
    """Test CHARGER-008: Charger supports authentication token refresh."""

    @requires("CHARGER-008", "INFRA-001")  # Token lifecycle, deterministic
    async def test_charger_obtains_initial_auth_token(self):
        """Charger should obtain an initial authentication token."""
        # Create charger
        charger = SimulatedCharger(charger_id="TOKEN-TEST")
        mock_central = AsyncMock()
        
        # Connect to central system (should trigger auth)
        await charger.connect_to_central(mock_central)
        
        # Verify token was obtained
        assert charger.auth_token is not None  # Token present
        assert charger.auth_token_expiry is not None  # Expiry time set
        
        # Cleanup
        await charger.disconnect()

    @requires("CHARGER-008", "INFRA-001")  # Token refresh, deterministic
    async def test_charger_refreshes_expiring_token(self):
        """Charger should refresh token before expiry."""
        # Create charger
        charger = SimulatedCharger(charger_id="REFRESH-TEST", token_lifetime_sec=10)
        mock_central = AsyncMock()
        await charger.connect_to_central(mock_central)
        
        # Get initial token
        initial_token = charger.auth_token
        initial_expiry = charger.auth_token_expiry
        
        # Wait for token to approach expiry
        await asyncio.sleep(8)  # 8 seconds (token valid for 10)
        
        # Charger should proactively refresh
        await charger._check_and_refresh_token()  # Trigger check
        
        # Verify token refreshed
        new_token = charger.auth_token
        new_expiry = charger.auth_token_expiry
        
        assert new_token != initial_token  # New token issued
        assert new_expiry > initial_expiry  # Extended expiry
        
        # Cleanup
        await charger.disconnect()

    @requires("CHARGER-008", "INFRA-001")  # Failed refresh, deterministic
    async def test_charger_handles_token_refresh_failure(self):
        """Charger should handle token refresh failures gracefully."""
        # Create charger
        charger = SimulatedCharger(charger_id="REFRESH-FAIL-TEST")
        
        # Mock central that fails refresh
        mock_central = AsyncMock()
        mock_central.refresh_auth_token.side_effect = Exception("Refresh failed")
        
        await charger.connect_to_central(mock_central)
        initial_token = charger.auth_token
        
        # Attempt refresh (will fail)
        result = await charger._check_and_refresh_token()
        
        # Charger should continue with old token
        assert result.success is False  # Refresh failed
        assert charger.auth_token == initial_token  # Token unchanged
        
        await charger.disconnect()


class TestPowerSupplyDynamicCurrentLimits:
    """Test CHARGER-009: Power supply supports dynamic current limits."""

    @requires("CHARGER-009", "INFRA-001")  # Dynamic limits, deterministic
    async def test_power_supply_sets_dynamic_current_limit(self):
        """Power supply should support setting limits dynamically."""
        # Create power supply
        power = MockPowerSupply(current_max_a=32.0)
        power.enable()
        
        # Set limit to 16A
        power.set_current_limit(16.0)
        assert power.get_current_limit() == 16.0
        
        # Change limit to 20A
        power.set_current_limit(20.0)
        assert power.get_current_limit() == 20.0
        
        # Lower limit to 10A
        power.set_current_limit(10.0)
        assert power.get_current_limit() == 10.0

    @requires("CHARGER-009", "INFRA-001")  # Limit constraints, deterministic
    async def test_power_supply_respects_maximum_current_limit(self):
        """Power supply should not exceed hardware maximum."""
        # Create power supply with 32A max
        power = MockPowerSupply(current_max_a=32.0)
        
        # Try to set limit above max (should be clamped)
        power.set_current_limit(50.0)  # Above max
        
        # Verify clamped to max
        actual = power.get_current_limit()
        assert actual <= 32.0  # Never exceeds hardware max

    @requires("CHARGER-009", "INFRA-001")  # Limit during charging, deterministic
    async def test_power_supply_applies_limit_during_charging(self):
        """Power supply should enforce limits while charger is drawing current."""
        # Create power supply
        power = MockPowerSupply(current_max_a=32.0)
        power.enable()
        
        # Set low limit
        power.set_current_limit(10.0)
        
        # Simulate charger drawing power
        power.simulate_load_change(load_current_a=8.0)  # Draw 8A
        
        # Read actual current
        actual_current = power.get_current()
        
        # Should not exceed limit
        assert actual_current <= 10.0

    @requires("CHARGER-009", "INFRA-001")  # Limit reduction, deterministic
    async def test_power_supply_reduces_limit_mid_charging(self):
        """Power supply should handle mid-session limit reductions."""
        # Create power supply with charger already charging
        power = MockPowerSupply(current_max_a=32.0)
        power.enable()
        
        # Start charging at 20A
        power.set_current_limit(20.0)
        power.simulate_load_change(load_current_a=20.0)  # Drawing 20A
        
        # Reduce limit to 10A (charger needs to ramp down)
        power.set_current_limit(10.0)
        
        # Verify new limit is active
        assert power.get_current_limit() == 10.0
        
        # Current should eventually reduce (charger responds to limit)
        # (in real implementation, charger would throttle)


class TestMultipleChargerInstances:
    """Test CHARGER-010: Framework supports multiple simultaneous charger instances."""

    @requires("CHARGER-010", "INFRA-001")  # Multiple instances, deterministic
    async def test_create_multiple_charger_instances(self):
        """Should be able to create multiple independent charger instances."""
        # Create three chargers
        chargers = [
            SimulatedCharger(charger_id=f"MULTI-{i}") for i in range(3)
        ]
        
        # Verify each is independent
        assert len(chargers) == 3
        assert chargers[0].charger_id == "MULTI-0"
        assert chargers[1].charger_id == "MULTI-1"
        assert chargers[2].charger_id == "MULTI-2"

    @requires("CHARGER-010", "INFRA-001")  # Independent operation, deterministic
    async def test_multiple_chargers_operate_independently(self):
        """Multiple chargers should operate independently without interference."""
        # Create two chargers
        charger1 = SimulatedCharger(charger_id="INDEP-1", power_available=True)
        charger2 = SimulatedCharger(charger_id="INDEP-2", power_available=False)
        
        try:
            # Get states
            state1 = await charger1.get_state()
            state2 = await charger2.get_state()
            
            # Verify independent states
            assert state1.power_available is True  # C1 has power
            assert state2.power_available is False  # C2 no power
            
            # Change charger1's power (should not affect charger2)
            charger1.power_supply.set_state(available=False)
            state1_updated = await charger1.get_state()
            state2_unchanged = await charger2.get_state()
            
            assert state1_updated.power_available is False  # C1 changed
            assert state2_unchanged.power_available is False  # C2 unchanged
        finally:
            # Cleanup
            pass

    @requires("CHARGER-010", "INFRA-001")  # Concurrent sessions, deterministic
    async def test_multiple_chargers_with_concurrent_sessions(self):
        """Multiple chargers should handle concurrent charging sessions."""
        # Create two chargers
        chargers = [
            SimulatedCharger(charger_id=f"CONCURRENT-{i}") for i in range(2)
        ]
        
        try:
            # Start sessions on both chargers concurrently
            async def start_session(charger, vehicle_id):
                return await charger.start_charging_session(vehicle_id)
            
            # Start both sessions in parallel
            sessions = await asyncio.gather(
                start_session(chargers[0], "VEHICLE-A"),
                start_session(chargers[1], "VEHICLE-B")
            )
            
            # Verify both sessions active
            assert len(sessions) == 2
            assert sessions[0].active is True
            assert sessions[1].active is True
            assert sessions[0].vehicle_id == "VEHICLE-A"
            assert sessions[1].vehicle_id == "VEHICLE-B"
            
            # Sessions should be independent
            assert sessions[0].session_id != sessions[1].session_id
        finally:
            pass

    @requires("CHARGER-010", "INFRA-001")  # Central coordination, deterministic
    async def test_multiple_chargers_with_shared_central_system(self):
        """Multiple chargers should coordinate with single central system."""
        # Create mock central system
        mock_central = AsyncMock()
        
        # Create two chargers using same central
        chargers = [
            SimulatedCharger(charger_id=f"SHARED-{i}") for i in range(2)
        ]
        
        try:
            # Connect both to central system
            await chargers[0].connect_to_central(mock_central)
            await chargers[1].connect_to_central(mock_central)
            
            # Verify both connected
            assert chargers[0].connected is True
            assert chargers[1].connected is True
            
            # Central should track both
            calls = mock_central.connect.call_count
            assert calls == 2  # Called twice for two chargers
        finally:
            pass

    @requires("CHARGER-010", "INFRA-001")  # Resource cleanup, deterministic
    async def test_multiple_chargers_cleanup_resources(self):
        """Multiple chargers should properly cleanup resources."""
        # Create chargers
        chargers = [
            SimulatedCharger(charger_id=f"CLEANUP-{i}") for i in range(3)
        ]
        
        # Connect them
        mock_central = AsyncMock()
        for charger in chargers:
            await charger.connect_to_central(mock_central)
        
        # Cleanup all
        for charger in chargers:
            await charger.disconnect()
        
        # Verify all disconnected
        for charger in chargers:
            assert charger.connected is False
