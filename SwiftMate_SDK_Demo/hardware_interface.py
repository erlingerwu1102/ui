"""Hardware abstraction for emergency stop.
Provides a pluggable `EmergencyStopController` with backends for GPIO or Modbus.
Backends are optional; if required libraries are unavailable the controller will
log and return False for engage/release.
"""

import logging

logger = logging.getLogger(__name__)


class EmergencyStopController:
    def __init__(self, backend=None, config=None):
        # backend: 'gpio', 'modbus', or None for simulated
        self.backend = backend
        self.config = config or {}
        self._engaged = False
        # attempt to initialize backend if available
        if backend == 'gpio':
            try:
                import RPi.GPIO as GPIO
                self.GPIO = GPIO
                self.pin = int(self.config.get('gpio_pin', 17))
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self.pin, GPIO.OUT)
                logger.info(f"GPIO e-stop initialized on pin {self.pin}")
                self._backend_ready = True
            except Exception as e:
                logger.warning(f"GPIO backend unavailable: {e}")
                self._backend_ready = False
        elif backend == 'modbus':
            try:
                from pymodbus.client.sync import ModbusTcpClient
                self.ModbusClient = ModbusTcpClient
                self.modbus_host = self.config.get('modbus_host')
                self.modbus_port = int(self.config.get('modbus_port', 502))
                logger.info(f"Modbus e-stop configured for {self.modbus_host}:{self.modbus_port}")
                self._backend_ready = True
            except Exception as e:
                logger.warning(f"Modbus backend unavailable: {e}")
                self._backend_ready = False
        else:
            # simulated / no-op backend
            self._backend_ready = False

    def engage(self):
        """Engage hardware e-stop. Returns True if command issued/accepted."""
        try:
            if self.backend == 'gpio' and self._backend_ready:
                try:
                    self.GPIO.output(self.pin, self.GPIO.HIGH)
                    self._engaged = True
                    logger.info("GPIO e-stop engaged")
                    return True
                except Exception as e:
                    logger.exception(f"Failed to engage GPIO e-stop: {e}")
                    return False
            elif self.backend == 'modbus' and self._backend_ready:
                try:
                    client = self.ModbusClient(self.modbus_host, port=self.modbus_port)
                    client.connect()
                    # write single coil or register depending on device; this is a placeholder
                    client.write_coil(1, True)
                    client.close()
                    self._engaged = True
                    logger.info("Modbus e-stop engaged")
                    return True
                except Exception as e:
                    logger.exception(f"Failed to engage Modbus e-stop: {e}")
                    return False
            else:
                # fallback: mark engaged (simulated)
                logger.info("Simulated hardware e-stop engaged (no backend)")
                self._engaged = True
                return True
        except Exception:
            return False

    def release(self):
        """Release hardware e-stop."""
        try:
            if self.backend == 'gpio' and self._backend_ready:
                try:
                    self.GPIO.output(self.pin, self.GPIO.LOW)
                    self._engaged = False
                    logger.info("GPIO e-stop released")
                    return True
                except Exception as e:
                    logger.exception(f"Failed to release GPIO e-stop: {e}")
                    return False
            elif self.backend == 'modbus' and self._backend_ready:
                try:
                    client = self.ModbusClient(self.modbus_host, port=self.modbus_port)
                    client.connect()
                    client.write_coil(1, False)
                    client.close()
                    self._engaged = False
                    logger.info("Modbus e-stop released")
                    return True
                except Exception as e:
                    logger.exception(f"Failed to release Modbus e-stop: {e}")
                    return False
            else:
                logger.info("Simulated hardware e-stop released (no backend)")
                self._engaged = False
                return True
        except Exception:
            return False

    def is_engaged(self):
        return bool(self._engaged)
