"""
Custom exception types for the charger test framework.

These exceptions distinguish between product/behavior failures (AssertionError)
and infrastructure/test-framework failures (InfrastructureError, SafetyLimitError).
"""


class ChargerLabError(Exception):
    """Base exception for all chargerlab errors."""
    pass


class InfrastructureError(ChargerLabError):
    """
    Raised when the test infrastructure (communication, instruments, network) fails.
    
    Examples: VISA timeout, power supply unreachable, central system unavailable,
    WebSocket connection lost.
    
    These errors can be retried by the test framework.
    """
    pass


class SafetyLimitError(ChargerLabError):
    """
    Raised when a safety limit is violated (e.g., voltage setpoint exceeds max).
    
    The driver guarantees that no command is sent to the instrument when
    this error is raised (safe-state principle).
    """
    pass
