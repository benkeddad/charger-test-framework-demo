"""
Mock power supply for testing without real hardware or pyvisa-sim.

Simulates a power supply in memory without relying on external libraries.
Used in integration tests to avoid pyvisa-sim setup complexity.
"""

import logging  # Logging framework

from chargerlab.drivers import PowerSupply  # Abstract base class

# Logger for this module
logger = logging.getLogger(__name__)


class MockPowerSupply(PowerSupply):
    """
    Mock power supply that simulates behavior in memory.
    
    Maintains internal state (voltage, output enabled) and simulates
    SCPI commands without actual hardware or pyvisa connection.
    
    Args:
        max_voltage (float): Maximum allowed voltage (safety limit)
    """
    
    def __init__(self, max_voltage: float = 300.0) -> None:
        """
        Initialize mock power supply.
        
        Args:
            max_voltage: Maximum allowed voltage (V)
        """
        # Configuration
        self.max_voltage = max_voltage  # Safety limit
        
        # Internal state
        self._voltage = 0.0  # Current voltage setpoint (V)
        self._output_enabled = False  # Output state (True = on, False = off)
        
        logger.info(f"MockPowerSupply initialized (max {max_voltage}V)")
    
    async def idn(self) -> str:
        """
        Return mock device identification.
        
        Returns:
            str: Device ID string
        """
        # Return a mock identification string
        idn = "MOCK,PSU-1000,SN0001,1.0"
        logger.debug(f"IDN query: {idn}")
        return idn
    
    async def set_voltage(self, voltage: float) -> None:
        """
        Set the output voltage.
        
        Args:
            voltage: Target voltage in volts
        
        Raises:
            ValueError: If voltage is out of range
        """
        # Validate: voltage must be >= 0
        if voltage < 0:
            raise ValueError(f"Voltage {voltage}V is below minimum (0V)")
        
        # Validate: voltage must be <= max_voltage
        if voltage > self.max_voltage:
            raise ValueError(
                f"Voltage {voltage}V exceeds maximum ({self.max_voltage}V)"
            )
        
        # Set voltage in internal state
        self._voltage = voltage
        logger.debug(f"Voltage set to {voltage}V")
    
    async def get_voltage(self) -> float:
        """
        Read the current output voltage.
        
        Returns:
            float: Current voltage in volts
        """
        logger.debug(f"Voltage query: {self._voltage}V")
        return self._voltage
    
    async def output(self, enabled: bool) -> None:
        """
        Enable or disable the output.
        
        Args:
            enabled: True to enable, False to disable
        """
        # Update internal state
        self._output_enabled = enabled
        state_str = "ON" if enabled else "OFF"
        logger.debug(f"Output set to {state_str}")
    
    async def get_output(self) -> bool:
        """
        Read the current output state.
        
        Returns:
            bool: True if output is enabled, False otherwise
        """
        logger.debug(f"Output query: {self._output_enabled}")
        return self._output_enabled
    
    async def safe_state(self) -> None:
        """
        Set the power supply to a safe state: output off, voltage 0 V.
        """
        # Turn off output first
        await self.output(False)
        
        # Set voltage to 0V
        await self.set_voltage(0.0)
        
        logger.info("Safe state achieved: output OFF, voltage 0V")
    
    async def close(self) -> None:
        """
        Close the connection (no-op for mock).
        """
        logger.debug("MockPowerSupply connection closed")
