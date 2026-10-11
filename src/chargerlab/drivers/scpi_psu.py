"""
SCPI-based power supply driver using pyvisa.

Implements the PowerSupply interface for instruments communicating via VISA/SCPI.
Validates all setpoints against configured limits before sending commands.
"""

from chargerlab.drivers import PowerSupply  # noqa: F401 (imported for subclass)
