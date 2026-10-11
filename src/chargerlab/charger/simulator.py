"""
Simulated EV charger with OCPP client and vehicle-side control.

The charger connects to a central system, manages charging sessions,
monitors power supply voltage, and enforces charging rules based on IEC 61851.
"""

import asyncio  # Async runtime
import json  # JSON serialization for OCPP
import logging  # Logging framework
from datetime import datetime, timedelta  # Timestamps
from typing import Optional  # Optional types

import websockets  # WebSocket client library

from chargerlab.charger.states import CpState  # Vehicle connection states (A/B/C/E/F)
from chargerlab.drivers import PowerSupply  # Power supply interface
from chargerlab.errors import InfrastructureError  # Communication errors

# Logger for this module
logger = logging.getLogger(__name__)


class SimulatedCharger:
    """
    Simulated EV charger with OCPP 1.6J client and power supply control.

    Represents an AC charging station that:
    1. Connects to a central system via OCPP/WebSocket
    2. Manages charging sessions (authorize, start, stop)
    3. Controls vehicle-interface state (A/B/C/E/F per IEC 61851)
    4. Uses PowerSupply driver to control output voltage/current
    5. Enforces charging rules (e.g., power only in state C)

    Used in Phase 2 tests to verify the full charger workflow:
    Boot → Connect Vehicle → Authorize → Start Session → Supply Power → Stop Session

    Example:
        >>> psu = ScpiPowerSupply(...)
        >>> charger = SimulatedCharger(
        ...     charger_id="TEST-CHARGER-001",
        ...     psu=psu,
        ...     ocpp_server_url="ws://127.0.0.1:9000/TEST-CHARGER-001"
        ... )
        >>> await charger.connect_to_backend()
        >>> await charger.set_cp_state(CpState.B)  # Vehicle connected
        >>> await charger.authorize_tag("test-tag")
        >>> await charger.start_transaction()
        >>> await charger.set_cp_state(CpState.C)  # Ready to charge
        >>> # Power delivered while in state C
        >>> await charger.stop_transaction()
        >>> await charger.disconnect()
    """

    def __init__(
        self,
        charger_id: str,  # Unique identifier for this charger
        psu: PowerSupply,  # Power supply driver (for voltage/current control)
        ocpp_server_url: str,  # Central system WebSocket URL
    ) -> None:
        """
        Initialize the simulated charger.

        Args:
            charger_id: Unique charger identifier (used in OCPP messages)
            psu: PowerSupply instance for controlling output
            ocpp_server_url: WebSocket URL of central system (e.g., ws://localhost:9000/ABC)
        """
        # Charger identity
        self.charger_id = charger_id  # Unique ID
        self.psu = psu  # Power supply driver
        self.ocpp_server_url = ocpp_server_url  # Central system URL

        # Connection state
        self.websocket = None  # WebSocket to central system (set on connect)
        self.cp_state = CpState.A  # Current vehicle interface state (starts at A: disconnected)
        self.message_counter = 0  # Counter for generating unique OCPP message IDs

        # Session state
        self.authorized_tag = None  # Current authorized RFID tag
        self.transaction_id = None  # Current transaction ID (from central system)
        self.transaction_active = False  # Whether transaction is active

        # Timekeeping
        self.boot_time = None  # When charger booted
        self.last_heartbeat = None  # When last heartbeat was sent

    async def connect_to_backend(self) -> None:
        """
        Connect to the central system via OCPP/WebSocket.

        Establishes connection and sends BootNotification.
        Call this before any charger operations.

        Raises:
            InfrastructureError: If connection fails or central system unreachable
        """
        try:
            # Log connection attempt
            logger.info(f"Connecting charger {self.charger_id} to {self.ocpp_server_url}")

            # Open WebSocket connection to central system
            self.websocket = await websockets.connect(self.ocpp_server_url)

            # Send BootNotification to central system
            await self._send_call(
                "BootNotification",  # Action: charger is booting
                {
                    "chargeBoxSerialNumber": self.charger_id,  # Charger identity
                    "chargePointVendor": "SimulatedCharger",  # Vendor name
                    "chargePointModel": "SC-1.0",  # Model name
                    "firmwareVersion": "1.0.0",  # Firmware version
                    "iccid": None,  # SIM card ID (not used)
                    "imsi": None,  # Mobile network ID (not used)
                },
            )

            # Record boot time
            self.boot_time = datetime.utcnow()
            logger.info(f"Charger {self.charger_id} connected and booted")

        except Exception as e:
            raise InfrastructureError(f"Failed to connect to central system: {e}") from e

    async def disconnect(self) -> None:
        """
        Disconnect from the central system.

        Closes WebSocket connection. Call in test teardown.
        """
        if self.websocket:
            await self.websocket.close()  # Close connection
            logger.info(f"Charger {self.charger_id} disconnected")

    async def set_cp_state(self, state: CpState) -> None:
        """
        Set the vehicle-interface state (A/B/C/E/F per IEC 61851).

        Transitions the charger to the given state. Enforces IEC 61851 rules:
        - State A: Vehicle disconnected (output OFF, voltage 0V)
        - State B: Vehicle connected but not authorized (output OFF)
        - State C: Vehicle connected and authorized (power delivery allowed)
        - State E: Error detected (output OFF, emergency stop)
        - State F: Charger unavailable (output OFF)

        Args:
            state: Target CpState

        Raises:
            ValueError: If invalid state transition
        """
        # Log state change
        old_state = self.cp_state
        self.cp_state = state
        logger.info(f"Charger {self.charger_id}: {old_state.name} → {state.name}")

        # Enforce IEC 61851 rules based on new state
        if state == CpState.A:
            # State A: No vehicle, output OFF
            await self.psu.output(False)  # Disable power output
            await self.psu.set_voltage(0.0)  # Voltage to 0V

        elif state == CpState.B:
            # State B: Vehicle connected, output OFF (waiting for authorization)
            await self.psu.output(False)  # Disable power output
            await self.psu.set_voltage(0.0)  # Voltage to 0V

        elif state == CpState.C:
            # State C: Vehicle ready to charge, power allowed
            # PSU should be already configured; just enable output
            if not self.transaction_active:
                logger.warning("Entered state C without active transaction")
                return

            # Enable output to deliver power
            await self.psu.output(True)
            logger.info(f"Power delivery enabled (state C, txn {self.transaction_id})")

        elif state in (CpState.E, CpState.F):
            # State E/F: Error or unavailable, safe state (output OFF, 0V)
            await self.psu.safe_state()
            logger.warning(f"Charger in error/unavailable state: {state.name}")

    async def authorize_tag(self, tag_id: str) -> bool:
        """
        Authorize an RFID tag (simulates user presenting badge).

        Sends Authorize message to central system and records the tag.
        Returns True if central system accepts the tag.

        Args:
            tag_id: RFID tag identifier

        Returns:
            True if authorized, False otherwise

        Raises:
            InfrastructureError: If communication fails
        """
        try:
            # Send Authorize message to central system
            response = await self._send_call(
                "Authorize",  # Action: request authorization
                {
                    "idTag": tag_id,  # Tag to authorize
                },
            )

            # Check if authorization was accepted
            tag_info = response.get("idTagInfo", {})
            status = tag_info.get("status", "Rejected")

            if status == "Accepted":
                # Store authorized tag
                self.authorized_tag = tag_id
                logger.info(f"Tag {tag_id} authorized for charger {self.charger_id}")
                return True
            else:
                logger.warning(f"Tag {tag_id} rejected (status: {status})")
                return False

        except Exception as e:
            raise InfrastructureError(f"Authorize request failed: {e}") from e

    async def start_transaction(self, voltage: float = 230.0) -> Optional[int]:
        """
        Start a charging transaction.

        Sends StartTransaction to central system to begin a charging session.
        Central system returns a transaction ID for this session.

        This method:
        1. Must be called after authorize_tag()
        2. Configures PSU to output the requested voltage
        3. Sends StartTransaction message
        4. Records transaction ID from response

        Args:
            voltage: Initial voltage to set (default 230V, typical mains)

        Returns:
            Transaction ID from central system, or None if failed

        Raises:
            InfrastructureError: If communication fails
            RuntimeError: If no authorized tag
        """
        # Verify we have an authorized tag
        if not self.authorized_tag:
            raise RuntimeError("Cannot start transaction without authorized tag")

        try:
            # Configure PSU for power delivery (but don't enable output yet)
            # Output will be enabled when transitioning to state C
            await self.psu.set_voltage(voltage)
            logger.debug(f"PSU configured: {voltage}V")

            # Send StartTransaction message
            response = await self._send_call(
                "StartTransaction",  # Action: begin charging session
                {
                    "connectorId": 1,  # Connector number (always 1 for single-connector charger)
                    "idTag": self.authorized_tag,  # Authorized tag ID
                    "meterStart": 0,  # Energy meter reading at start (0 kWh)
                    "timestamp": datetime.utcnow().isoformat() + "Z",  # Current time
                },
            )

            # Extract transaction ID from response
            self.transaction_id = response.get("transactionId")
            self.transaction_active = True

            logger.info(
                f"Transaction started: ID {self.transaction_id} "
                f"for tag {self.authorized_tag}"
            )
            return self.transaction_id

        except Exception as e:
            raise InfrastructureError(f"StartTransaction failed: {e}") from e

    async def stop_transaction(self) -> None:
        """
        Stop the current charging transaction.

        Sends StopTransaction to central system to end the charging session.
        Disables PSU output and transitions to state A (disconnected).

        Raises:
            InfrastructureError: If communication fails
            RuntimeError: If no active transaction
        """
        # Verify we have an active transaction
        if not self.transaction_active or not self.transaction_id:
            raise RuntimeError("No active transaction to stop")

        try:
            # Disable power output
            await self.psu.output(False)
            logger.debug("Power output disabled")

            # Send StopTransaction message
            await self._send_call(
                "StopTransaction",  # Action: end charging session
                {
                    "transactionId": self.transaction_id,  # Transaction to stop
                    "idTag": self.authorized_tag,  # Tag used in transaction
                    "meterStop": 0,  # Energy meter reading at stop (0 kWh, simulated)
                    "timestamp": datetime.utcnow().isoformat() + "Z",  # Current time
                },
            )

            # Clear transaction state
            self.transaction_active = False
            self.transaction_id = None
            self.authorized_tag = None

            # Return to state A (disconnected)
            await self.set_cp_state(CpState.A)

            logger.info("Transaction stopped")

        except Exception as e:
            raise InfrastructureError(f"StopTransaction failed: {e}") from e

    async def _send_call(self, action: str, payload: dict) -> dict:
        """
        Send an OCPP CALL message and wait for CALLRESULT response.

        OCPP message format:
          CALL:       [2, msg_id, action, payload]
          CALLRESULT: [3, msg_id, response_payload]

        This is the low-level method used by public charger methods.

        Args:
            action: OCPP action name (e.g., "Authorize", "StartTransaction")
            payload: Message payload (action-specific data)

        Returns:
            Response payload from central system

        Raises:
            InfrastructureError: If send/receive fails or websocket closed
        """
        # Verify connected
        if not self.websocket:
            raise InfrastructureError("Not connected to central system")

        try:
            # Generate unique message ID
            self.message_counter += 1
            msg_id = str(self.message_counter)  # Message ID as string

            # Build OCPP CALL message: [2, msg_id, action, payload]
            message = [2, msg_id, action, payload]

            # Send message to central system
            await self.websocket.send(json.dumps(message))
            logger.debug(f"Sent OCPP CALL: {action} (id={msg_id})")

            # Wait for CALLRESULT response
            # Response will be: [3, msg_id, response_payload] or [4, msg_id, error_code, error_msg]
            response_data = await asyncio.wait_for(
                self.websocket.recv(),  # Receive response
                timeout=5.0,  # Wait max 5 seconds
            )

            # Parse response
            response = json.loads(response_data)

            # Check response type
            if len(response) >= 3:
                response_type = response[0]

                if response_type == 3:  # CALLRESULT
                    # Success response: [3, msg_id, response_payload]
                    response_payload = response[2]
                    logger.debug(f"Received CALLRESULT for {action}")
                    return response_payload

                elif response_type == 4:  # CALLERROR
                    # Error response: [4, msg_id, error_code, error_msg]
                    error_code = response[2] if len(response) > 2 else "Unknown"
                    error_msg = response[3] if len(response) > 3 else ""
                    raise InfrastructureError(
                        f"OCPP error {error_code}: {error_msg}"
                    )

            # Unexpected response format
            raise InfrastructureError(f"Invalid OCPP response: {response}")

        except asyncio.TimeoutError:
            raise InfrastructureError(f"Timeout waiting for {action} response")
        except (websockets.exceptions.ConnectionClosed, OSError) as e:
            raise InfrastructureError(f"WebSocket error: {e}")
