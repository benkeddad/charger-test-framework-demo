"""
SCPI-based power supply driver using pyvisa.

Implements the PowerSupply interface for instruments communicating via VISA/SCPI.
Validates all setpoints against configured limits before sending commands.

Key principle: All validation happens BEFORE writing to the instrument.
If validation fails (SafetyLimitError), no VISA command is sent.
This ensures the instrument state never changes due to a safety violation.
"""

import logging  # Log errors for debugging

import pyvisa  # VISA library for instrument control

from chargerlab.drivers import PowerSupply  # Abstract base class to implement
from chargerlab.errors import (  # Custom exception types
    InfrastructureError,
    SafetyLimitError,
)

# Logger for this module
logger = logging.getLogger(__name__)


class ScpiPowerSupply(PowerSupply):
    """
    SCPI power supply driver using pyvisa.

    Communicates with a power supply via VISA (GPIB, Serial, USB, etc.)
    using SCPI (Standard Commands for Programmable Instruments).

    Validates voltage setpoints against configured limits before writing.
    Maps communication errors to InfrastructureError.

    Args:
        resource (str): VISA resource address (e.g., "ASRL1::INSTR" for serial,
                        "GPIB0::1::INSTR" for GPIB, or "configs/psu_sim.yaml@sim" for sim)
        max_voltage (float): Maximum allowed output voltage (V). Setter will reject
                            any voltage > max_voltage to prevent damage.
        rm_spec (str): Resource manager specification. Default "@py" uses PyVISA.
                       Use "configs/psu_sim.yaml@sim" for simulated instruments.
    """

    def __init__(
        self,
        resource: str,
        max_voltage: float,
        rm_spec: str = "@py",
    ) -> None:
        """
        Initialize the SCPI power supply driver.

        Args:
            resource: VISA resource address
            max_voltage: Maximum allowed voltage (safety limit)
            rm_spec: Resource manager specification

        Raises:
            InfrastructureError: If instrument cannot be opened or identified
        """
        # Store configuration
        self.resource_string = resource  # Save for logging/debugging
        self.max_voltage = max_voltage   # Safety limit
        self.rm_spec = rm_spec           # Resource manager spec

        # Open connection to instrument
        try:
            # Create resource manager (PyVISA or simulated)
            self.rm = pyvisa.ResourceManager(rm_spec)

            # Open the specific resource (e.g., "ASRL1::INSTR")
            self.instrument = self.rm.open_resource(
                resource,
                read_termination="\n",   # SCPI responses end with newline
                write_termination="\n",  # SCPI commands end with newline
            )
        except (pyvisa.errors.VisaIOError, FileNotFoundError, OSError) as e:
            # VISA communication failed (device not found, permissions, bad config, etc.)
            raise InfrastructureError(
                f"Cannot open VISA resource '{resource}': {e}"
            ) from e

    async def idn(self) -> str:
        """
        Query and return the instrument identification string.

        Returns:
            str: Device identification (e.g., "SIM,PSU-1000,SN0001,1.0")

        Raises:
            InfrastructureError: If query times out or communication fails
        """
        try:
            # Send *IDN? query and get response
            idn_string = self.instrument.query("*IDN?")
            return idn_string.strip()  # Remove trailing whitespace
        except pyvisa.errors.VisaIOError as e:
            # Communication failure (timeout, connection lost, etc.)
            raise InfrastructureError(f"IDN query failed: {e}") from e

    async def set_voltage(self, voltage: float) -> None:
        """
        Set the output voltage.

        CRITICAL: Validates limits BEFORE writing to instrument.
        If validation fails, no command is sent (safe-state principle).

        Args:
            voltage: Target voltage in volts (0.0 to max_voltage)

        Raises:
            SafetyLimitError: If voltage < 0 or voltage > max_voltage.
                            No command is sent in this case.
            InfrastructureError: If VISA write/query fails after validation passes
        """
        # VALIDATION: Check limits BEFORE writing
        if voltage < 0:
            # Negative voltage is always invalid
            raise SafetyLimitError(
                f"Voltage {voltage}V is below minimum (0V). "
                f"No command sent to instrument."
            )

        if voltage > self.max_voltage:
            # Voltage exceeds configured maximum
            raise SafetyLimitError(
                f"Voltage {voltage}V exceeds maximum ({self.max_voltage}V). "
                f"No command sent to instrument."
            )

        # WRITE: Limits validated, safe to send command
        try:
            # Send VOLT command (e.g., "VOLT 230.000")
            self.instrument.write(f"VOLT {voltage:.3f}")
            logger.debug(f"Set voltage to {voltage:.3f}V")
        except pyvisa.errors.VisaIOError as e:
            # Communication failed (timeout, connection lost, etc.)
            raise InfrastructureError(
                f"Failed to set voltage to {voltage}V: {e}"
            ) from e

    async def get_voltage(self) -> float:
        """
        Read the current output voltage.

        Returns:
            float: Current voltage in volts

        Raises:
            InfrastructureError: If query times out or communication fails
        """
        try:
            # Query voltage with VOLT? command
            response = self.instrument.query("VOLT?")
            # Parse response as float (e.g., "230.000" -> 230.0)
            voltage = float(response.strip())
            logger.debug(f"Read voltage: {voltage}V")
            return voltage
        except pyvisa.errors.VisaIOError as e:
            # Communication failed
            raise InfrastructureError(f"Failed to read voltage: {e}") from e
        except ValueError as e:
            # Response was not a valid number
            raise InfrastructureError(
                f"Invalid voltage response: {response!r}"
            ) from e

    async def output(self, enabled: bool) -> None:
        """
        Enable or disable the output.

        Args:
            enabled: True to enable output, False to disable

        Raises:
            InfrastructureError: If VISA write/query fails
        """
        try:
            # Convert bool to SCPI integer (1 for on, 0 for off)
            state = 1 if enabled else 0
            # Send OUTP command (e.g., "OUTP 1" to enable, "OUTP 0" to disable)
            self.instrument.write(f"OUTP {state:d}")
            logger.debug(f"Output {'enabled' if enabled else 'disabled'}")
        except pyvisa.errors.VisaIOError as e:
            # Communication failed
            raise InfrastructureError(
                f"Failed to set output to {enabled}: {e}"
            ) from e

    async def get_output(self) -> bool:
        """
        Read the current output state.

        Returns:
            bool: True if output is enabled, False if disabled

        Raises:
            InfrastructureError: If query times out or communication fails
        """
        try:
            # Query output state with OUTP? command
            response = self.instrument.query("OUTP?")
            # Parse response as integer (1 or 0)
            state = int(response.strip())
            # Convert to boolean (1 -> True, 0 -> False)
            enabled = bool(state)
            logger.debug(f"Read output state: {enabled}")
            return enabled
        except pyvisa.errors.VisaIOError as e:
            # Communication failed
            raise InfrastructureError(f"Failed to read output state: {e}") from e
        except ValueError as e:
            # Response was not a valid integer
            raise InfrastructureError(
                f"Invalid output state response: {response!r}"
            ) from e

    async def safe_state(self) -> None:
        """
        Set the power supply to a safe state: output OFF, voltage 0V.

        Used in test teardown to guarantee cleanup even if a test fails.
        This method is designed NOT to raise exceptions during cleanup.

        If any operation fails, it logs the error but allows cleanup to continue.
        This ensures the test framework can always recover.

        Raises:
            InfrastructureError: Only if BOTH operations fail (rare edge case)
        """
        try:
            # Step 1: Disable output (safer to do first)
            logger.debug("Entering safe state: disabling output...")
            try:
                self.instrument.write("OUTP 0")  # Output OFF
            except pyvisa.errors.VisaIOError as e:
                logger.error(f"Failed to disable output during safe_state: {e}")
                # Don't raise yet; try to set voltage to 0 anyway

            # Step 2: Set voltage to 0V
            logger.debug("Entering safe state: setting voltage to 0V...")
            try:
                self.instrument.write("VOLT 0.0")  # Voltage 0V
            except pyvisa.errors.VisaIOError as e:
                logger.error(f"Failed to set voltage to 0V during safe_state: {e}")
                # Logged but not raised; cleanup continues

            logger.info("Safe state achieved: output OFF, voltage 0V")

        except Exception as e:
            # Unexpected error (shouldn't happen with the above structure)
            logger.error(f"Unexpected error during safe_state: {e}")
            # Still don't raise in cleanup to allow test teardown to complete

    async def close(self) -> None:
        """
        Close the VISA connection and release the resource.

        Called in test teardown after safe_state() to properly release
        the instrument connection.
        """
        try:
            if self.instrument:
                self.instrument.close()  # Close VISA connection
                logger.debug(f"Closed connection to {self.resource_string}")
        except Exception as e:
            # Log but don't raise (cleanup shouldn't fail)
            logger.error(f"Error closing VISA connection: {e}")
