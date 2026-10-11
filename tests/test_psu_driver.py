"""
Unit tests for SCPI power supply driver.

Tests the ScpiPowerSupply driver against a simulated instrument (pyvisa-sim).
Covers:
  1. Instrument identification (IDN query)
  2. Voltage set/get round-trip
  3. Output enable/disable round-trip
  4. Safety limit enforcement (setpoint > max raises SafetyLimitError)
  5. Safe state behavior (leaves output off, voltage 0V)
  6. Error handling (communication failures map to InfrastructureError)
"""

import os  # For finding config files
from pathlib import Path  # For file path handling

import pytest  # Testing framework
import pyvisa.errors  # VISA exception types

from chargerlab.drivers.scpi_psu import ScpiPowerSupply  # Driver under test
from chargerlab.errors import (  # Expected exception types
    InfrastructureError,
    SafetyLimitError,
)


# =====================================================================
# Fixtures (test setup/teardown)
# =====================================================================


@pytest.fixture
def config_file() -> str:
    """
    Return path to the simulated PSU configuration file.

    The config file (psu_sim.yaml) defines SCPI command responses
    for the simulated power supply.
    """
    # Find the config file relative to this test file
    test_dir = Path(__file__).parent.parent  # Go up to project root
    config_path = test_dir / "configs" / "psu_sim.yaml"
    # Verify file exists (will fail test with clear error if not)
    assert config_path.exists(), f"Config file not found: {config_path}"
    return str(config_path)  # Return as string for pyvisa


@pytest.fixture
async def psu(config_file: str) -> ScpiPowerSupply:
    """
    Create a ScpiPowerSupply instance connected to the simulated instrument.

    The resource string "ASRL1::INSTR@sim" tells pyvisa to:
      - ASRL1::INSTR = serial port 1 (simulated)
      - @sim = use pyvisa-sim backend (not real hardware)
      - Configuration loaded from config_file

    The fixture automatically calls close() after test completes.
    """
    # Format resource manager spec with config file path
    rm_spec = f"{config_file}@sim"

    # Create driver connected to simulated PSU
    driver = ScpiPowerSupply(
        resource="ASRL1::INSTR",  # Serial port 1 (from psu_sim.yaml)
        max_voltage=1000.0,        # Max 1000V (safety limit)
        rm_spec=rm_spec,           # Use simulator with config
    )

    # Yield to test (test runs with 'psu' fixture available)
    yield driver

    # Cleanup: close connection after test completes
    await driver.close()


# =====================================================================
# Test: Identification (IDN)
# =====================================================================


@pytest.mark.asyncio
async def test_idn_query(psu: ScpiPowerSupply) -> None:
    """
    Test that IDN query returns the correct identification string.

    The simulated PSU responds with "SIM,PSU-1000,SN0001,1.0" as defined
    in psu_sim.yaml.
    """
    # Query instrument ID
    result = await psu.idn()

    # Verify response matches expected value
    assert result == "SIM,PSU-1000,SN0001,1.0", (
        f"Expected 'SIM,PSU-1000,SN0001,1.0', got '{result}'"
    )

    # Log for evidence
    print(f"✓ IDN: {result}")


# =====================================================================
# Test: Voltage Set/Get Round-Trip
# =====================================================================


@pytest.mark.asyncio
async def test_set_voltage_valid(psu: ScpiPowerSupply) -> None:
    """
    Test setting voltage within valid range (0-1000V).

    Should accept any voltage between 0 and max_voltage without raising.
    """
    # Set voltage to 230V (common mains voltage)
    await psu.set_voltage(230.0)

    # Read back the voltage
    actual = await psu.get_voltage()

    # Verify it was set correctly (within tolerance for simulator)
    assert abs(actual - 230.0) < 0.01, (
        f"Expected 230.0V, got {actual}V"
    )

    # Log for evidence
    print(f"✓ Set voltage to 230V, read back {actual}V")


@pytest.mark.asyncio
async def test_set_voltage_zero(psu: ScpiPowerSupply) -> None:
    """
    Test setting voltage to 0V (safe state).

    0V is the minimum allowed value and commonly used for shutdown.
    """
    # First set to non-zero
    await psu.set_voltage(500.0)

    # Then set to 0V
    await psu.set_voltage(0.0)

    # Verify 0V was set
    actual = await psu.get_voltage()
    assert actual < 0.01, f"Expected ~0V, got {actual}V"

    # Log for evidence
    print(f"✓ Set voltage to 0V, read back {actual}V")


@pytest.mark.asyncio
async def test_set_voltage_max(psu: ScpiPowerSupply) -> None:
    """
    Test setting voltage to the maximum allowed value.

    max_voltage is configured at driver creation time.
    """
    # Set to maximum
    await psu.set_voltage(psu.max_voltage)

    # Read back
    actual = await psu.get_voltage()

    # Verify success (within tolerance)
    assert abs(actual - psu.max_voltage) < 0.01, (
        f"Expected {psu.max_voltage}V, got {actual}V"
    )

    # Log for evidence
    print(f"✓ Set voltage to max ({psu.max_voltage}V), read back {actual}V")


# =====================================================================
# Test: Output Enable/Disable Round-Trip
# =====================================================================


@pytest.mark.asyncio
async def test_output_enable_disable(psu: ScpiPowerSupply) -> None:
    """
    Test enabling and disabling the output.

    Initial state should be OFF; enable changes it to ON; disable returns to OFF.
    """
    # Initial state: should be OFF (disabled)
    initial = await psu.get_output()
    assert not initial, "Expected output initially disabled"

    # Enable output
    await psu.output(True)
    enabled = await psu.get_output()
    assert enabled, "Expected output enabled after output(True)"

    # Disable output
    await psu.output(False)
    disabled = await psu.get_output()
    assert not disabled, "Expected output disabled after output(False)"

    # Log for evidence
    print("✓ Output enable/disable round-trip works")


# =====================================================================
# Test: Safety Limit Enforcement
# =====================================================================


@pytest.mark.asyncio
async def test_set_voltage_exceeds_max_raises_error(psu: ScpiPowerSupply) -> None:
    """
    Test that setting voltage above max_voltage raises SafetyLimitError.

    CRITICAL: No VISA command should be sent when SafetyLimitError is raised.
    This test verifies the safe-state principle: validation before write.
    """
    # Try to set voltage above maximum
    with pytest.raises(SafetyLimitError):
        # max_voltage is 1000.0, try to set 1001.0
        await psu.set_voltage(1001.0)

    # Verify no command was sent by checking instrument still has previous value
    # (if a command had been sent, voltage would have been 1001V, not 500V)
    # First set a known value
    await psu.set_voltage(500.0)

    # Try to exceed limit
    with pytest.raises(SafetyLimitError):
        await psu.set_voltage(1500.0)

    # Verify voltage is still 500V (no command was sent)
    actual = await psu.get_voltage()
    assert abs(actual - 500.0) < 0.01, (
        f"Voltage changed despite SafetyLimitError! Was 500V, now {actual}V"
    )

    # Log for evidence
    print("✓ SafetyLimitError prevents voltage above max (no command sent)")


@pytest.mark.asyncio
async def test_set_voltage_negative_raises_error(psu: ScpiPowerSupply) -> None:
    """
    Test that setting negative voltage raises SafetyLimitError.

    Negative voltage is always invalid regardless of max_voltage setting.
    """
    # Set PSU to known state first (some tests may have set it to 500V)
    await psu.set_voltage(0.0)

    # Try to set negative voltage
    with pytest.raises(SafetyLimitError):
        await psu.set_voltage(-10.0)

    # Verify voltage is still 0V (no command was sent)
    actual = await psu.get_voltage()
    assert actual < 0.01, f"Expected 0V after failed set, got {actual}V"

    # Log for evidence
    print("✓ SafetyLimitError prevents negative voltage (no command sent)")


# =====================================================================
# Test: Safe State Behavior
# =====================================================================


@pytest.mark.asyncio
async def test_safe_state_leaves_output_off_voltage_zero(
    psu: ScpiPowerSupply,
) -> None:
    """
    Test that safe_state() leaves the PSU in known safe state.

    Safe state is defined as:
      - Output: OFF (disabled)
      - Voltage: 0V

    Used in test teardown to guarantee PSU is safe regardless of test result.
    """
    # Set PSU to non-safe state (high voltage, output on)
    await psu.set_voltage(800.0)
    await psu.output(True)

    # Verify it's in non-safe state
    assert await psu.get_voltage() > 100.0  # High voltage
    assert await psu.get_output()  # Output is on

    # Call safe_state()
    await psu.safe_state()

    # Verify PSU is now in safe state
    voltage = await psu.get_voltage()
    output = await psu.get_output()

    assert voltage < 0.01, f"After safe_state(), voltage should be ~0V, got {voltage}V"
    assert not output, "After safe_state(), output should be OFF"

    # Log for evidence
    print("✓ safe_state() sets output OFF and voltage 0V")


# =====================================================================
# Test: Error Handling
# =====================================================================


@pytest.mark.asyncio
async def test_idn_error_maps_to_infrastructure_error(
    config_file: str,
) -> None:
    """
    Test that communication errors (timeouts, etc.) map to InfrastructureError.

    We test this by creating a driver and attempting to use an invalid config.
    pyvisa-sim will fail when parsing the config, which should be caught
    as InfrastructureError.
    """
    # Try with a non-existent config file (will fail at ResourceManager init)
    rm_spec = "C:\\nonexistent\\path\\psu_sim.yaml@sim"

    # Try to open resource manager with bad config
    try:
        with pytest.raises(InfrastructureError):
            psu_bad = ScpiPowerSupply(
                resource="ASRL1::INSTR",
                max_voltage=1000.0,
                rm_spec=rm_spec,  # Non-existent config path
            )
    except InfrastructureError:
        # Expected: bad config path raises InfrastructureError
        pass

    # Log for evidence
    print("✓ InfrastructureError raised for bad resource config")


# =====================================================================
# Test: Multiple Sequential Operations
# =====================================================================


@pytest.mark.asyncio
async def test_sequence_of_operations(psu: ScpiPowerSupply) -> None:
    """
    Test a realistic sequence of operations (like in a real charging test).

    1. Check identification
    2. Set voltage to safe level
    3. Enable output
    4. Verify voltage and output are set
    5. Disable output
    6. Return to safe state
    """
    # Step 1: Identify
    idn = await psu.idn()
    assert "PSU" in idn, f"Invalid IDN: {idn}"

    # Step 2: Set voltage (without output)
    await psu.set_voltage(230.0)

    # Step 3: Enable output
    await psu.output(True)

    # Step 4: Verify state
    assert await psu.get_voltage() > 200, "Voltage should be ~230V"
    assert await psu.get_output(), "Output should be ON"

    # Step 5: Disable output
    await psu.output(False)
    assert not await psu.get_output(), "Output should be OFF"

    # Step 6: Safe state
    await psu.safe_state()
    assert await psu.get_voltage() < 0.01, "Voltage should be 0V"
    assert not await psu.get_output(), "Output should be OFF"

    # Log for evidence
    print("✓ Realistic operation sequence completed successfully")
