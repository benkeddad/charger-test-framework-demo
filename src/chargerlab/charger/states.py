"""
EV charger vehicle-interface states per IEC 61851.

States represent the connection and charging readiness status of the vehicle.
"""

from enum import Enum


class CpState(Enum):
    """
    Vehicle connection and charging permission states.
    
    Mapped to IEC 61851-1 control-pilot states A–F.
    """

    # State A: No vehicle connected
    A = "not_connected"

    # State B: Vehicle connected, not ready to charge
    B = "connected_not_ready"

    # State C: Vehicle connected and ready to charge (external charger decision to allow)
    C = "ready_to_charge"

    # State E: Charger detected an error condition
    E = "error"

    # State F: Charger unavailable or in maintenance
    F = "unavailable"
