"""AMQP 1.0 server using Qpid Proton with non-blocking asyncio integration.

Implements a lightweight AMQP 1.0 broker that:
- Listens on port 6698 (configurable)
- Receives messages on configured channels
- Logs all received messages to stdout
- Integrates with FastAPI's asyncio event loop via do_work()
"""

import logging
import threading
import time
from contextlib import asynccontextmanager
from typing import Optional

from proton.handlers import MessagingHandler
from proton.reactor import Container

from .config import get_settings
from .interfaces import AMQPAddress, IPv4Address

logger = logging.getLogger(__name__)


class AMQPMessageHandler(MessagingHandler):
    """Handles incoming AMQP messages using Qpid Proton Reactor API."""

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.config = self.settings.get_config()

        # Collect all channel addresses we should receive on
        self._receive_addresses: set[AMQPAddress] = set()
        for app_name, channels in self.config.applications.items():
            for channel in channels:
                self._receive_addresses.add(AMQPAddress(channel.channel))

        logger.info(
            "AMQP handler initialized, will receive on: %s",
            self._receive_addresses,
        )

        # For shutdown signaling
        self._stopping = False

    def on_start(self, event):
        """Set up listener for incoming connections."""
        # URL format for listen: amqp://host:port
        url = f"amqp://{self.config.host}:{self.config.amqp_port}"
        event.container.listen(url)
        logger.info(
            "AMQP listener created on %s:%d", self.config.host, self.config.amqp_port
        )

        # Create receiver links for all configured channels
        for addr in self._receive_addresses:
            event.container.create_receiver(addr)
        logger.info("AMQP receiver links created for: %s", self._receive_addresses)

    def on_message(self, event):
        """Process an incoming AMQP message."""
        if self._stopping or event.delivery is None:
            return

        message = event.message

        try:
            timestamp = event.timestamp
            source = message.address or "unknown"
            subject = message.subject or "no subject"
            message_id = message.message_id or "no-id"
            content_type = message.content_type or "unknown"

            # Get message body
            body = message.body
            if isinstance(body, bytes):
                body_preview = f"<binary: {len(body)} bytes>"
            elif isinstance(body, str):
                body_preview = body[:500] if len(body) > 500 else body
            elif body is not None:
                body_preview = str(body)[:500]
            else:
                body_preview = "<empty>"

            logger.info(
                "[AMQP] %s | id=%s | source=%s | subject=%s | type=%s | body=%s",
                timestamp,
                message_id,
                source,
                subject,
                content_type,
                body_preview,
            )

            # Accept the message
            event.delivery.accept()

        except Exception as e:
            logger.error("[AMQP] Error processing message: %s", e)
            event.delivery.reject()


class NonBlockingAMQPContainer:
    """Non-blocking AMQP container that integrates with asyncio."""

    def __init__(self, host: IPv4Address | str = "0.0.0.0", port: int = 6698):
        self.host = IPv4Address(host)
        self.port = port
        self.handler = AMQPMessageHandler()
        self.container = Container(self.handler)

        self._thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._acceptor = None

    def _process_reactor(self):
        """Process reactor events in a loop until shutdown."""
        logger.info("AMQP reactor processing thread started")

        try:
            # Start the container with listen
            url = f"amqp://{self.host}:{self.port}"
            self._acceptor = self.container.listen(url)
            logger.info("AMQP listener created on %s:%d", self.host, self.port)

            # Create receiver links
            for addr in self.handler._receive_addresses:
                self.container.create_receiver(addr)

            # Main event loop
            while not self._shutdown_event.is_set():
                # Process events with a short timeout (non-blocking)
                processed = self.container.do_work(timeout=0.1)

                # Small sleep to prevent busy-waiting
                if not processed:
                    time.sleep(0.01)

        except Exception as e:
            logger.error("AMQP reactor error: %s", e)
        finally:
            # Clean shutdown
            if self._acceptor:
                self._acceptor.close()
            self.container.stop()

            logger.info("AMQP reactor processing thread stopped")

    def start(self):
        """Start the AMQP server in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("AMQP server already running")
            return

        self._shutdown_event.clear()
        self._thread = threading.Thread(
            target=self._process_reactor, daemon=True, name="AMQP-Reactor"
        )
        self._thread.start()
        logger.info("AMQP server started on %s:%d", self.host, self.port)

    def stop(self):
        """Stop the AMQP server gracefully."""
        if self._thread is None or not self._thread.is_alive():
            return

        logger.info("Stopping AMQP server...")
        self._shutdown_event.set()

        # Wait for thread to finish with timeout
        self._thread.join(timeout=5.0)

        if self._thread.is_alive():
            logger.warning("AMQP server did not stop gracefully")
            # Force cleanup of resources
            self._cleanup_resources()
        else:
            logger.info("AMQP server stopped")

    def _cleanup_resources(self):
        """Clean up resources when graceful shutdown fails."""
        try:
            if hasattr(self, "_acceptor") and self._acceptor:
                self._acceptor.close()
            if hasattr(self, "container") and self.container:
                self.container.stop()
        except Exception as e:
            logger.error("Error during resource cleanup: %s", e)

    @asynccontextmanager
    async def lifespan(self):
        """Context manager for FastAPI lifespan integration."""
        self.start()
        try:
            yield
        finally:
            self.stop()


# Global container instance
_amqp_container: Optional[NonBlockingAMQPContainer] = None


def get_amqp_container() -> NonBlockingAMQPContainer:
    """Get or create the global AMQP container instance."""
    global _amqp_container

    if _amqp_container is None:
        settings = get_settings()
        config = settings.get_config()
        _amqp_container = NonBlockingAMQPContainer(
            host=config.host, port=config.amqp_port
        )

    return _amqp_container


@asynccontextmanager
async def lifespan_amqp(app):
    """FastAPI lifespan manager for AMQP server."""
    container = get_amqp_container()
    container.start()
    try:
        yield
    finally:
        container.stop()


# Legacy compatibility function
def start_amqp_server(
    host: IPv4Address | str = "0.0.0.0", port: int = 6698
) -> threading.Thread:
    """Start the AMQP 1.0 server in a background daemon thread.

    Note: This uses the legacy blocking run() method in a thread.
    For new code, use NonBlockingAMQPContainer instead.

    DEPRECATED: This function will be removed in future versions.
    Use NonBlockingAMQPContainer instead.
    """
    logger.warning(
        "DEPRECATED: Using legacy start_amqp_server - this function will be removed in future versions. Use NonBlockingAMQPContainer instead."
    )

    def run_server():
        handler = AMQPMessageHandler()
        container = Container(handler)
        url = f"amqp://{host}:{port}"
        container.listen(url)
        try:
            container.run()
        except Exception as e:
            logger.error("AMQP server error: %s", e)

    thread = threading.Thread(target=run_server, args=(), daemon=True)
    thread.start()
    logger.info("AMQP server thread started on port %d", port)
    return thread
