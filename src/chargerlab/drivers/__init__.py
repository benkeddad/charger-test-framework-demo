"""
Abstract base class for power supply instruments.

Defines the interface that all power supply drivers must implement,
ensuring that production and test implementations can be swapped.
"""

from abc import ABC, abstractmethod


class PowerSupply(ABC):
    """
    Abstract interface for a power supply instrument.
    
    All methods that interact with the instrument should:
    - Validate limits before writing (raise SafetyLimitError if violated)
    - Map communication errors to InfrastructureError
    - Never send commands that would leave the instrument in an unsafe state
    """

    @abstractmethod
    async def idn(self) -> str:
        """
        Query the instrument identification string.
        
        Returns:
            str: Device ID (e.g., "SIM,PSU-1000,SN0001,1.0")
        
        Raises:
            InfrastructureError: If the VISA query fails or times out.
        """
        pass

    @abstractmethod
    async def set_voltage(self, voltage: float) -> None:
        """
        Set the output voltage.
        
        Args:
            voltage: Target voltage in volts.
        
        Raises:
            SafetyLimitError: If voltage < 0 or voltage > max_voltage.
                              No command is sent in this case.
            InfrastructureError: If the VISA write/query fails.
        """
        pass

    @abstractmethod
    async def get_voltage(self) -> float:
        """
        Read the current output voltage.
        
        Returns:
            float: Current voltage in volts.
        
        Raises:
            InfrastructureError: If the VISA query fails or times out.
        """
        pass

    @abstractmethod
    async def output(self, enabled: bool) -> None:
        """
        Enable or disable the output.
        
        Args:
            enabled: True to enable, False to disable.
        
        Raises:
            InfrastructureError: If the VISA write/query fails.
        """
        pass

    @abstractmethod
    async def get_output(self) -> bool:
        """
        Read the current output state.
        
        Returns:
            bool: True if output is enabled, False otherwise.
        
        Raises:
            InfrastructureError: If the VISA query fails or times out.
        """
        pass

    @abstractmethod
    async def safe_state(self) -> None:
        """
        Set the power supply to a safe state: output off, voltage 0 V.
        
        Used in test teardown to guarantee safe cleanup even if a test fails.
        This method must not raise exceptions; if a command fails, it should
        log the error but not propagate it.
        
        Raises:
            InfrastructureError: If the operations fail (but logged, not raised
                                by default in cleanup).
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Close the VISA connection.
        
        Used in test teardown to release the instrument resource.
        """
        pass
