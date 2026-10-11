"""
Mock OCPP 1.6J central system for testing charger behavior.

Runs a WebSocket server that accepts OCPP messages from the charger,
records them with timestamps, and provides async helpers for test assertions.
"""

import asyncio  # Async runtime
import json  # JSON serialization for OCPP messages
import logging  # Logging framework
from datetime import datetime  # Timestamp generation
from typing import Any, Dict, List, Optional  # Type hints
from collections import defaultdict  # Message grouping

import websockets  # WebSocket server library
from websockets.server import WebSocketServerProtocol  # WebSocket connection type

# Logger for this module
logger = logging.getLogger(__name__)


class OcppMessage:
    """
    Represents a single OCPP message (request or response).
    
    OCPP uses a 3-element array: [type, message_id, payload]
    where type is 2 (CALL/request) or 3 (CALLRESULT/response).
    """

    def __init__(
        self,
        direction: str,  # "rx" (received) or "tx" (transmitted)
        msg_type: int,  # 2=CALL, 3=CALLRESULT, 4=CALLERROR
        msg_id: str,  # Message ID for request/response matching
        action: str,  # OCPP action name (e.g., "Boot", "Authorize")
        payload: Dict[str, Any],  # Message payload (chargeBoxSerialNumber, etc.)
        timestamp: Optional[datetime] = None,  # When message occurred
    ) -> None:
        """Initialize OCPP message record."""
        self.direction = direction  # "rx" or "tx"
        self.msg_type = msg_type  # OCPP message type
        self.msg_id = msg_id  # Message identifier
        self.action = action  # OCPP action
        self.payload = payload  # Message content
        self.timestamp = timestamp or datetime.utcnow()  # Recording time

    def __repr__(self) -> str:
        """Return human-readable message summary."""
        return (
            f"OcppMessage({self.direction} {self.action} "
            f"id={self.msg_id} @ {self.timestamp.isoformat()})"
        )


class MockCentralSystem:
    """
    Mock OCPP 1.6J central system (charging backend).

    Runs a WebSocket server on localhost that:
    1. Accepts connections from chargers
    2. Records all OCPP messages (Boot, Authorize, StartTransaction, etc.)
    3. Provides async methods to query messages for test assertions
    4. Responds to charger requests with configurable responses

    Used in Phase 2 tests to verify charger behavior without a real backend.

    Example:
        >>> cs = MockCentralSystem(port=9000)
        >>> await cs.start()
        >>> # ... charger connects and sends messages ...
        >>> messages = await cs.get_messages("Boot")
        >>> assert len(messages) == 1
        >>> await cs.stop()
    """

    def __init__(self, port: int = 9000, host: str = "127.0.0.1") -> None:
        """
        Initialize the mock central system.

        Args:
            port: WebSocket server port (default 9000)
            host: Bind address (default 127.0.0.1 for localhost)
        """
        # Server configuration
        self.port = port  # WebSocket port
        self.host = host  # Bind address
        self.server = None  # WebSocket server object (set on start())

        # Message storage
        self.messages: List[OcppMessage] = []  # All messages (rx and tx)
        self.connected_chargers: Dict[str, WebSocketServerProtocol] = {}  # Active connections
        
        # Transaction ID counter (incremented for each StartTransaction)
        self.next_transaction_id = 1  # Start at 1

    async def start(self) -> None:
        """
        Start the WebSocket server.

        Listens on self.host:self.port for charger connections.
        Each connection handler processes incoming OCPP messages.
        """
        # Create WebSocket server
        self.server = await websockets.serve(
            self._handle_charger_connection,  # Handler for new connections
            self.host,  # Bind to this host
            self.port,  # Bind to this port
        )
        logger.info(f"MockCentralSystem started on ws://{self.host}:{self.port}")

    async def stop(self) -> None:
        """
        Stop the WebSocket server and close all connections.

        Called in test teardown to clean up resources.
        """
        if self.server:
            self.server.close()  # Stop accepting new connections
            await self.server.wait_closed()  # Wait for shutdown
            logger.info("MockCentralSystem stopped")

    async def _handle_charger_connection(
        self, websocket: WebSocketServerProtocol
    ) -> None:
        """
        Handle a new charger connection.

        Called by the WebSocket server when a charger connects.
        Receives messages, records them, and responds.

        Args:
            websocket: WebSocket connection to charger
        """
        try:
            # Log connection
            charger_id = None
            logger.debug(f"Charger connected from {websocket.remote_address}")

            # Receive messages until charger disconnects
            async for message in websocket:
                # Parse OCPP message (JSON array)
                try:
                    data = json.loads(message)  # Parse JSON
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from charger: {message}")
                    continue

                # OCPP message format: [type, msg_id, action, payload]
                # Type 2 = CALL (request from charger to CS)
                if len(data) >= 3 and data[0] == 2:
                    msg_type = data[0]  # Type: 2 = CALL
                    msg_id = data[1]  # Message ID (for matching responses)
                    action = data[2]  # Action name (e.g., "BootNotification")
                    payload = data[3] if len(data) > 3 else {}  # Message payload

                    # Special handling for BootNotification (charger identification)
                    if action == "BootNotification":
                        charger_id = payload.get("chargeBoxSerialNumber", "unknown")
                        self.connected_chargers[charger_id] = websocket

                    # Record received message
                    msg = OcppMessage(
                        direction="rx",  # Received from charger
                        msg_type=msg_type,
                        msg_id=msg_id,
                        action=action,
                        payload=payload,
                    )
                    self.messages.append(msg)
                    logger.debug(f"Received: {msg}")

                    # Send response (CALLRESULT: [3, msg_id, payload])
                    response = await self._get_response_for(action)
                    response_msg = [3, msg_id, response]  # [type, id, response]

                    # Send response to charger
                    try:
                        await websocket.send(json.dumps(response_msg))

                        # Record sent message
                        msg_out = OcppMessage(
                            direction="tx",  # Transmitted to charger
                            msg_type=3,  # CALLRESULT
                            msg_id=msg_id,
                            action=f"{action}Response",
                            payload=response,
                        )
                        self.messages.append(msg_out)
                        logger.debug(f"Sent: {msg_out}")
                    except Exception as e:
                        logger.error(f"Failed to send response: {e}")

        except websockets.exceptions.ConnectionClosed:
            logger.debug(f"Charger disconnected")
        except Exception as e:
            logger.error(f"Error handling charger connection: {e}", exc_info=True)

    async def _get_response_for(self, action: str) -> Dict[str, Any]:
        """
        Generate a response payload for the given OCPP action.

        Simulates the central system responding to charger requests.
        Returns appropriate response for each action type.

        Args:
            action: OCPP action name (e.g., "BootNotification", "Authorize")

        Returns:
            Response payload (dict)
        """
        # Map actions to default responses
        responses = {
            "BootNotification": {
                "status": "Accepted",  # Accept charger boot
                "interval": 300,  # Heartbeat interval (seconds)
                "currentTime": datetime.utcnow().isoformat() + "Z",
            },
            "Heartbeat": {
                "currentTime": datetime.utcnow().isoformat() + "Z",
            },
            "Authorize": {
                "idTagInfo": {
                    "status": "Accepted",  # Accept authorization
                    "expiryDate": "2099-12-31T23:59:59Z",
                }
            },
            "StartTransaction": {
                "transactionId": self.next_transaction_id,  # Increment for each transaction
                "idTagInfo": {"status": "Accepted"},
            },
            "StopTransaction": {
                "idTagInfo": {"status": "Accepted"},
            },
        }

        # Increment transaction ID for next StartTransaction request
        if action == "StartTransaction":
            self.next_transaction_id += 1

        # Return response for this action, or empty dict if unknown
        return responses.get(action, {})

    async def get_messages(self, action: Optional[str] = None) -> List[OcppMessage]:
        """
        Get all recorded OCPP messages, optionally filtered by action.

        Used in tests to assert that charger sent expected messages.

        Args:
            action: Filter by action name (e.g., "Boot", "Authorize"), or None for all

        Returns:
            List of OcppMessage objects matching the filter
        """
        if action is None:
            return self.messages  # Return all messages

        # Filter messages by action
        return [msg for msg in self.messages if action in msg.action]

    async def get_message_count(self, action: str) -> int:
        """
        Count how many times a specific OCPP action was sent.

        Used in tests to verify charger behavior (e.g., "authorize should happen once").

        Args:
            action: OCPP action name to count

        Returns:
            Number of messages with this action
        """
        messages = await self.get_messages(action)
        return len(messages)

    async def wait_for_message(
        self, action: str, timeout: float = 5.0
    ) -> OcppMessage:
        """
        Wait for a specific OCPP message to arrive.

        Polls the message list until the action is found or timeout.
        Used in tests that need to wait for charger to send a message.

        Args:
            action: OCPP action to wait for
            timeout: Max seconds to wait (default 5.0)

        Returns:
            The OcppMessage that arrived

        Raises:
            asyncio.TimeoutError: If timeout expires before message arrives
        """
        start = asyncio.get_event_loop().time()  # Current time
        while True:
            # Check if message arrived
            messages = await self.get_messages(action)
            if messages:
                return messages[-1]  # Return most recent message

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed > timeout:
                raise asyncio.TimeoutError(
                    f"Timeout waiting for {action} message after {timeout}s"
                )

            # Wait a bit before polling again (avoid busy loop)
            await asyncio.sleep(0.1)
