"""
pytest configuration and fixtures for chargerlab tests.

Central place for:
- Async test setup via pytest-asyncio
- Shared fixtures (e.g., power supply, central system, charger)
- Test discovery settings
- Requirements traceability setup
"""

import asyncio  # Async runtime
import logging  # Logging framework
import os  # Environment variables
from typing import AsyncGenerator  # Type hint for async generators

import pytest  # pytest framework

from chargerlab.charger.central_system import MockCentralSystem  # Mock OCPP backend
from chargerlab.charger.simulator import SimulatedCharger  # Simulated charger
from chargerlab.drivers.mock_psu import MockPowerSupply  # Mock power supply for testing
from chargerlab.requirements.database import get_database  # Access requirements database

# Logger for this module
logger = logging.getLogger(__name__)

# Flag to track if requirements have been initialized
_requirements_initialized = False


def _initialize_requirements_once():
    """Initialize requirements database once on first pytest run.
    
    This prevents double-initialization when conftest is imported multiple times.
    """
    global _requirements_initialized  # Access global flag
    
    # If already initialized, skip (prevent double setup)
    if _requirements_initialized:
        return
    
    # Mark as initialized
    _requirements_initialized = True
    
    # Import and execute setup (only on first run)
    from chargerlab.requirements.test_requirements_setup import (
        setup_requirements,
        link_phase_1_tests,
        link_phase_2_tests,
    )
    
    # Initialize database and link tests
    setup_requirements()  # Populate requirements database
    link_phase_1_tests()  # Link Phase 1 tests to requirements
    link_phase_2_tests()  # Link Phase 2 tests to requirements
    
    logger.info("Requirements database initialized")




# ============================================================================
# Pytest Configuration
# ============================================================================


def pytest_configure(config):
    """
    Register custom pytest markers and configure logging.

    Called once per test run. We define markers for test categorization:
    - integration: Tests that exercise multiple components
    - negative: Tests error and edge cases
    - boundary: Tests limits and extreme values
    - recovery: Tests error recovery and resilience
    """
    # Initialize requirements database (one-time setup)
    _initialize_requirements_once()
    
    # Set PYVISA_SIM_PATH before any tests import pyvisa
    # This tells pyvisa-sim to load our custom device config from YAML
    sim_path = os.path.join(
        os.path.dirname(__file__), "..", "configs", "psu_sim.yaml"
    )
    os.environ["PYVISA_SIM_PATH"] = sim_path
    logger.info(f"PYVISA_SIM_PATH set to: {sim_path}")

    # Markers are defined in pyproject.toml [tool.pytest.ini_options]
    # This ensures logging is set up for tests
    logging.basicConfig(
        level=logging.INFO,  # Show INFO and above
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


# ============================================================================
# Fixtures: Power Supply
# ============================================================================


@pytest.fixture
async def psu() -> AsyncGenerator[MockPowerSupply, None]:
    """
    Fixture: Mock power supply for testing.

    Provides a MockPowerSupply that simulates charging power supply behavior
    without requiring pyvisa-sim or real hardware. Maintains internal state for
    voltage and output, responding to method calls without external communication.

    Yields:
        MockPowerSupply instance

    Example:
        async def test_psu_voltage(psu):
            await psu.set_voltage(48.0)
            voltage = await psu.get_voltage()
            assert voltage == 48.0
    """
    try:
        # Create mock power supply with safety limit
        psu_instance = MockPowerSupply(max_voltage=300.0)

        # Ensure PSU is in safe state before test
        await psu_instance.safe_state()
        logger.info("PSU fixture initialized (mock)")

        yield psu_instance  # Provide to test

    finally:
        # Cleanup: ensure safe state and close connection
        try:
            await psu_instance.safe_state()  # Final safe state
            await psu_instance.close()  # Release resource
        except Exception as e:
            # Log cleanup errors but don't fail the test
            logger.warning(f"PSU cleanup error: {e}")


# ============================================================================
# Fixtures: Central System (Mock OCPP Backend)
# ============================================================================


@pytest.fixture
async def central_system() -> AsyncGenerator[MockCentralSystem, None]:
    """
    Fixture: Mock central system with OCPP/WebSocket server.

    Provides a MockCentralSystem listening on localhost:9000 (or next available port).
    Chargers connect here to exchange OCPP messages (Boot, Authorize, StartTransaction, etc.).

    This fixture:
    1. Creates MockCentralSystem instance
    2. Starts WebSocket server
    3. Provides to test (test can query messages, record events, etc.)
    4. Stops server after test completes

    Yields:
        MockCentralSystem instance with running server

    Example:
        async def test_charger_boot(central_system):
            charger_id = await central_system.wait_for_message(
                filter_action="BootNotification"
            )
            assert charger_id is not None
    """
    # Create central system instance
    cs = MockCentralSystem(
        host="127.0.0.1",  # Localhost only
        port=9000,  # Default OCPP port
    )

    try:
        # Start WebSocket server
        await cs.start()
        logger.info("Central system started: ws://127.0.0.1:9000")

        yield cs  # Provide to test

    finally:
        # Cleanup: stop server
        try:
            await cs.stop()
            logger.info("Central system stopped")
        except Exception as e:
            logger.warning(f"Error stopping central system: {e}")


# ============================================================================
# Fixtures: Simulated Charger
# ============================================================================


@pytest.fixture
async def charger(
    psu: MockPowerSupply,
    central_system: MockCentralSystem,
) -> AsyncGenerator[SimulatedCharger, None]:
    """
    Fixture: Simulated EV charger connected to PSU and central system.

    Provides a SimulatedCharger that:
    1. Connects to the central system via OCPP/WebSocket
    2. Controls the simulated PSU (voltage, current, output)
    3. Implements IEC 61851 state machine (A/B/C/E/F)
    4. Manages charging transactions

    Dependencies:
        - psu: MockPowerSupply (power output control)
        - central_system: MockCentralSystem (OCPP backend)

    Yields:
        SimulatedCharger instance, connected and booted

    Example:
        async def test_charging_session(charger):
            # Charger is already connected and booted
            await charger.set_cp_state(CpState.B)  # Vehicle connected
            assert await charger.authorize_tag("user-123")
            txn_id = await charger.start_transaction()
            assert txn_id is not None
    """
    # Create charger instance
    charger_id = "TEST-CHARGER-001"
    charger_instance = SimulatedCharger(
        charger_id=charger_id,  # Unique ID
        psu=psu,  # Power supply driver
        ocpp_server_url=f"ws://127.0.0.1:{central_system.port}/{charger_id}",
    )

    try:
        # Connect to central system and boot
        await charger_instance.connect_to_backend()
        logger.info(f"Charger fixture initialized: {charger_id}")

        yield charger_instance  # Provide to test

    finally:
        # Cleanup: stop transaction, return to safe state, disconnect
        try:
            if charger_instance.transaction_active:
                await charger_instance.stop_transaction()
        except Exception as e:
            logger.warning(f"Error stopping transaction during cleanup: {e}")

        try:
            await charger_instance.psu.safe_state()
        except Exception as e:
            logger.warning(f"Error putting PSU in safe state: {e}")

        try:
            await charger_instance.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting charger: {e}")
