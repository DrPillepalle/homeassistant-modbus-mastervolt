import logging
import asyncio
import struct
from homeassistant.components.sensor import SensorEntity
from datetime import timedelta

_LOGGER = logging.getLogger(__name__)

DOMAIN = "modbus_mastervolt"

def setup_platform(hass, config, add_entities, discovery_info=None):
    try:
        name = config.get("name", "Unnamed Device").lower().replace(" ", "_")

        idal = config.get("idal")
        idb = config.get("idb")
        tab = config.get("tab")
        var = config.get("var")
        rw = config.get("rw", 0)
        value = config.get("value", 0)
        scan_interval = config.get("scan_interval", 30)
        unit_of_measurement = config.get("unit_of_measurement", None)

        if None in (idal, idb, tab, var):
            _LOGGER.error("One or more parameters are missing from the configuration: idal=%s, idb=%s, tab=%s, var=%s", idal, idb, tab, var)
            return
        
        sensor = ModbusReadWriteSensor(name, hass, idal, idb, tab, var, rw, value, unit_of_measurement)
        add_entities([sensor], True)

        if isinstance(scan_interval, int):
            sensor.scan_interval = timedelta(seconds=scan_interval)
        else:
            _LOGGER.warning(f"Invalid type for scan_interval: {type(scan_interval)}. Expected int. Using default scan_interval.")

        hass.services.register(DOMAIN, "send_command", sensor.send_modbus_command)

    except Exception as e:
        _LOGGER.error(f"Error during sensor initialization: {e}")
        raise

class ModbusReadWriteSensor(SensorEntity):
    def __init__(self, name, hass, idal, idb, tab, var, rw, value, unit_of_measurement):
        self._name = name
        self._state = None
        self._hass = hass
        self._idal = idal
        self._idb = idb
        self._tab = tab
        self._var = var
        self.rw = rw
        self._value = value
        self._unit_of_measurement = unit_of_measurement
        
        # Add Attributes
        self._attributes = {
            "idal": self._idal,
            "idb": self._idb,
            "tab": self._tab,
            "var": self._var
        }

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state
    
    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    def update(self):
        if self.rw == 0:
            self.perform_modbus_read()

    def perform_modbus_read(self):
        hub_name = "modbus_hub1"
        slave = 1
        read_address = 0x0000
        read_count = 6
        write_address = 0x0000

        values = [
            *self.combine_values(),
            0x0000,
            0x0000
        ]

        hub = self._hass.data['modbus'][hub_name]
        client = hub._client

        try:
            read_write_result = asyncio.run_coroutine_threadsafe(
                client.readwrite_registers(
                    read_address=read_address,
                    read_count=read_count,
                    write_address=write_address,
                    values=values,
                    slave=slave
                ),
                self._hass.loop
            ).result()

        except Exception as e:
            _LOGGER.error(f"Error in Modbus read operation: {e}")
            return

        if read_write_result.isError():
            _LOGGER.error("Error during readwrite_registers operation")
            return

        # Retrieve the read registers
        read_registers = read_write_result.registers
        
        # Convert registers to bytes
        read_bytes = []
        for reg in read_registers:
            high_byte = (reg >> 8) & 0xFF  # Extract the high byte
            low_byte = reg & 0xFF  # Extract the low byte
            read_bytes.append(high_byte)
            read_bytes.append(low_byte)

        # Convert the bytes to hexadecimal format
        read_bytes_hex = [f'{byte:02X}' for byte in read_bytes]

        # Extract specific bytes for the value calculation
        if len(read_bytes_hex) >= 8:
            lo = read_bytes_hex[8]  
            mi = read_bytes_hex[9]  
            hi = read_bytes_hex[10]  
            exponent = read_bytes_hex[11]

            # Calculate the custom float value
            result = self.custom_bytes_to_float(lo, mi, hi, exponent)
            self._state = result  # Store the calculated value in the sensor state
        else:
            _LOGGER.error("Modbus response does not contain enough data.")

    def send_modbus_command(self, call):
        command_name = call.data.get("command_name", None)
        if not command_name:
            _LOGGER.error("No command_name provided in service call.")
            return

        # Retrieve the configuration of the specified entity
        entity_config = self._hass.states.get(f"sensor.{command_name}")
        if not entity_config:
            _LOGGER.error(f"Entity {command_name} not found.")
            return
              
        # Retrieve idal, idb, tab, var from the entity configuration
        idal = entity_config.attributes.get("idal")
        idb = entity_config.attributes.get("idb")
        tab = entity_config.attributes.get("tab")
        var = entity_config.attributes.get("var")

        if None in (idal, idb, tab, var):
            _LOGGER.error("One or more required parameters (idal, idb, tab, var) are missing in the entity configuration.")
            return

        self._idal = idal
        self._idb = idb
        self._tab = tab
        self._var = var
        
        hub_name = "modbus_hub1"
        slave = 1
        read_address = 0x0000
        read_count = 6
        write_address = 0x0001

        if isinstance(call, int):
            value = call  # Use the integer value directly
        elif call is None:
            return  # Do nothing if the function is called directly
        else:
            # Extract the value from the ServiceCall
            value = call.data.get('value', 0)  # Default to 0 if 'value' is not present

        lo, mi, hi, exp = self.float_to_bytes_little_endian(value)

        # Combine the bytes into registers
        register1 = (lo << 8) | mi
        register2 = (hi << 8) | exp

        values = [
            *self.combine_values(),
            register1,
            register2
        ]
        
        hub = self._hass.data['modbus'][hub_name]
        client = hub._client

        try:
            asyncio.run_coroutine_threadsafe(
                client.readwrite_registers(
                    read_address=read_address,
                    read_count=read_count,
                    write_address=write_address,
                    values=values,
                    slave=slave
                ),
                self._hass.loop
            ).result()

        except Exception as e:
            _LOGGER.error(f"Error in Modbus operation: {e}")
    
    def combine_values(self):
        db_byte1 = self._idb & 0xFF
        idb_byte2 = (self._idb >> 8) & 0xFF
        idb_byte3 = (self._idb >> 16) & 0xFF

        first_combined_value = (self._idal << 8) | idb_byte3
        second_combined_value = (idb_byte2 << 8) | db_byte1
        third_combined_value = self._tab & 0xFFFF
        fourth_combined_register = self._var & 0xFFFF

        return first_combined_value, second_combined_value, third_combined_value, fourth_combined_register

    @staticmethod
    def custom_bytes_to_float(lo, mi, hi, exponent):
        lo = int(lo, 16)
        mi = int(mi, 16)
        hi = int(hi, 16)
        exponent = int(exponent, 16)

        combined = (exponent << 24) | (hi << 16) | (mi << 8) | lo
        byte_array = combined.to_bytes(4, byteorder='big')
        float_value = struct.unpack('>f', byte_array)[0]

        return float_value

    @staticmethod
    def float_to_bytes_little_endian(float_num):
        """Converts a float number into 4 bytes little-endian, splitting into LO, MI, HI, and EXP.

        Args:
            float_num: The float number to convert.

        Returns:
            LO, MI, HI, and EXP representing the 4 bytes in little-endian format.
        """
        packed = struct.pack('<f', float_num)
        bytes_value = struct.unpack('4B', packed)

        lo, mi, hi, exp = bytes_value

        return lo, mi, hi, exp
