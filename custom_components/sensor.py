import logging
import asyncio
import struct
import threading
from homeassistant.components.sensor import SensorEntity
from datetime import timedelta

_LOGGER = logging.getLogger(__name__)

DOMAIN = "modbus_mastervolt"

# SCHRITT 7: kleine Pause nach jeder Modbus-Anfrage, damit der RS485-
# Transceiver zwischen zwei Transaktionen "durchatmen" kann. Bei Bedarf
# anpassen (z.B. 0.1 falls weiterhin isError-Meldungen auftreten).
_REQUEST_SETTLE_DELAY = 0.05

# SCHRITT 8: längere Pause nach einem SCHREIB-Befehl (send_command), damit
# das Gateway den Befehl auf den MasterBus bringen kann, bevor der nächste
# Sensor-Poll auf den Bus darf.
_WRITE_SETTLE_DELAY = 0.5

_LOCK_KEY = f"{DOMAIN}_bus_lock"

# SCHRITT 9: Lock für die Service-Registrierung. setup_platform() läuft für
# die 56 Sensoren PARALLEL auf mehreren SyncWorker-Threads. Der reine
# has_service-Check aus Schritt 4 ist ein Check-then-act-Race: alle Worker
# prüfen gleichzeitig, sehen alle "nicht registriert" und registrieren dann
# alle den Service (im Log sichtbar als 10x "erfolgreich initialisiert und
# registriert" innerhalb weniger Millisekunden). Die letzte Registrierung
# gewinnt und bindet den Service an eine ZUFÄLLIGE Sensor-Instanz.
_SERVICE_REGISTRATION_LOCK = threading.Lock()


def _get_bus_lock(hass):
    """Gibt den geteilten Bus-Lock zurück, einmalig auf dem Event-Loop von
    hass erzeugt.

    SCHRITT 7: Alle 56 Sensoren dieser Integration teilen sich denselben
    RS485-Bus über hub._client, was den eingebauten Lock des Home Assistant
    ModbusHub umgeht. Dieser Lock stellt sicher, dass immer nur eine
    readwrite_registers-Anfrage gleichzeitig unterwegs ist, egal von
    welchem Sensor sie kommt.
    """
    lock = hass.data.get(_LOCK_KEY)
    if lock is None:
        lock = asyncio.Lock()
        hass.data[_LOCK_KEY] = lock
    return lock


async def _locked_readwrite_registers(hass, client, settle_delay=_REQUEST_SETTLE_DELAY, **kwargs):
    """Serialisiert readwrite_registers-Aufrufe über alle Sensoren hinweg.

    SCHRITT 8: settle_delay ist pro Aufruf steuerbar - Lesezugriffe nutzen
    _REQUEST_SETTLE_DELAY, Schreibbefehle die längere _WRITE_SETTLE_DELAY.
    Die Pause läuft bewusst INNERHALB des Locks ab, damit der nächste
    Zugriff erst danach auf den Bus darf.
    """
    lock = _get_bus_lock(hass)
    async with lock:
        result = await client.readwrite_registers(**kwargs)
        # Kurze Pause, damit der RS485-Transceiver zwischen zwei
        # Transaktionen Zeit zum Umschalten hat, bevor der Lock freigegeben
        # wird und die nächste Anfrage rausgehen kann.
        await asyncio.sleep(settle_delay)
        return result

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
            # SCHRITT 1: reaktiviert - ein stillschweigender Abbruch ohne Log
            # macht es unmöglich zu sehen, warum ein Sensor plötzlich fehlt.
            _LOGGER.debug("Sensor '%s': one or more parameters are missing from the configuration: idal=%s, idb=%s, tab=%s, var=%s", name, idal, idb, tab, var)
            return
        
        sensor = ModbusReadWriteSensor(name, hass, idal, idb, tab, var, rw, value, unit_of_measurement)
        add_entities([sensor], True)

        if isinstance(scan_interval, int):
            sensor.scan_interval = timedelta(seconds=scan_interval)
        # SCHRITT 4 + SCHRITT 9: Service nur einmal registrieren, jetzt
        # thread-sicher. Check und Registrierung laufen unter einem Lock,
        # damit bei den parallel laufenden setup_platform()-Aufrufen
        # garantiert nur EIN Worker registriert. Seit Schritt 9 mutiert
        # send_modbus_command außerdem keine Instanz-Attribute mehr, sodass
        # es unerheblich ist, welche Sensor-Instanz den Service besitzt.
        with _SERVICE_REGISTRATION_LOCK:
            if not hass.services.has_service(DOMAIN, "send_command"):
                hass.services.register(DOMAIN, "send_command", sensor.send_modbus_command)
                _LOGGER.warning(f"Modbus Mastervolt Gateway: Programm erfolgreich initialisiert und registriert.")

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
        device_id = 1                   # früher: slave
        read_address = 0x0000
        read_count = 6
        write_address = 0x0000

        values = [
            *self.combine_values(),
            0x0000,
            0x0000
        ]

        # SCHRITT 3: Hub-/Client-Zugriff jetzt innerhalb des try-Blocks - ein
        # fehlender oder noch nicht initialisierter Hub warf hier vorher
        # einen unbehandelten KeyError statt einer sauberen Logmeldung.
        try:
            hub = self._hass.data['modbus'][hub_name]
            client = hub._client

            read_write_result = asyncio.run_coroutine_threadsafe(
                _locked_readwrite_registers(
                    self._hass,
                    client,
                    read_address=read_address,
                    read_count=read_count,
                    write_address=write_address,
                    values=values,
                    device_id=device_id            # früher: slave=slave
                ),
                self._hass.loop
            ).result()

        except KeyError:
            _LOGGER.error(
                "Modbus Hub '%s' nicht in hass.data['modbus'] gefunden. "
                "Prüfe, ob der Hub-Name mit deiner modbus:-Konfiguration übereinstimmt.",
                hub_name,
            )
            return
        except Exception as e:
            _LOGGER.error(f"Error in Modbus read operation: {e}")
            return

        if read_write_result.isError():
            _LOGGER.error("Error during readwrite_registers operation")
            return

        # Retrieve the read registers
        read_registers = read_write_result.registers

        # SCHRITT 8: Antwort-Validierung. Die ersten 4 Register der Antwort
        # enthalten den Anfrage-Header (idal/idb/tab/var). Passt der nicht
        # zur eigenen Anfrage, gehört die Antwort zu einer anderen
        # Transaktion. Dann wird der Wert verworfen und der bisherige
        # Sensorzustand bleibt unverändert erhalten.
        expected_header = list(self.combine_values())
        response_header = list(read_registers[0:4])
        if response_header != expected_header:
            _LOGGER.warning(
                "Sensor '%s': Modbus-Antwort gehört zu einer anderen Anfrage "
                "(Header %s, erwartet %s) - Wert verworfen, alter Zustand bleibt erhalten.",
                self._name,
                [f"0x{r:04X}" for r in response_header],
                [f"0x{r:04X}" for r in expected_header],
            )
            return

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

        # SCHRITT 9 (die eigentliche Fehlerursache): Bis hierhin wurden idal/
        # idb/tab/var der Service-Owner-Instanz überschrieben
        # (self._idal = idal usw.). Da die Service-Registrierung durch das
        # Race aus Schritt 4 auf einer ZUFÄLLIGEN Sensor-Instanz landen
        # konnte, wurde bei manchen Neustarts eine READ-Instanz (z.B.
        # mv_bat_cl_charge_tmp) zum Service-Owner. Ein send_command bog dann
        # deren Adressierung dauerhaft auf die Ziel-Entität um - der Sensor
        # las ab dem nächsten Poll den Breaker-Ampere-Wert statt des
        # Ladezustands. Jetzt bleiben die Werte lokal, keine Instanz wird
        # verändert.
        
        hub_name = "modbus_hub1"
        device_id = 1                      # früher: slave = 1
        read_address = 0x0000
        read_count = 6
        write_address = 0x0001

        # SCHRITT 2: toten isinstance(call, int)-Zweig entfernt - diese
        # Methode wird ausschließlich als HA-Service aufgerufen, `call` ist
        # hier immer ein ServiceCall-Objekt, nie ein int oder None.
        value = call.data.get('value', 0)  # Default to 0 if 'value' is not present

        lo, mi, hi, exp = self.float_to_bytes_little_endian(value)

        # Combine the bytes into registers
        register1 = (lo << 8) | mi
        register2 = (hi << 8) | exp

        values = [
            *self._combine_values_for(idal, idb, tab, var),
            register1,
            register2
        ]
        
        # SCHRITT 3 (Schreibpfad): gleiche Absicherung wie beim Lesepfad.
        try:
            hub = self._hass.data['modbus'][hub_name]
            client = hub._client

            asyncio.run_coroutine_threadsafe(
                _locked_readwrite_registers(
                    self._hass,
                    client,
                    # SCHRITT 8: nach einem Schreibbefehl längere Pause
                    # INNERHALB des Locks.
                    settle_delay=_WRITE_SETTLE_DELAY,
                    read_address=read_address,
                    read_count=read_count,
                    write_address=write_address,
                    values=values,
                    device_id=device_id            # früher: slave=slave
                ),
                self._hass.loop
            ).result()

        except KeyError:
            _LOGGER.error(
                "Modbus Hub '%s' nicht in hass.data['modbus'] gefunden. "
                "Prüfe, ob der Hub-Name mit deiner modbus:-Konfiguration übereinstimmt.",
                hub_name,
            )
        except Exception as e:
            _LOGGER.error(f"Error in Modbus operation: {e}")
    
    @staticmethod
    def _combine_values_for(idal, idb, tab, var):
        """SCHRITT 9: Registerberechnung als statische Methode mit expliziten
        Parametern, damit der Schreibpfad KEINE Instanz-Attribute mehr
        benötigt oder verändert."""
        db_byte1 = idb & 0xFF
        idb_byte2 = (idb >> 8) & 0xFF
        idb_byte3 = (idb >> 16) & 0xFF

        first_combined_value = (idal << 8) | idb_byte3
        second_combined_value = (idb_byte2 << 8) | db_byte1
        third_combined_value = tab & 0xFFFF
        fourth_combined_register = var & 0xFFFF

        return first_combined_value, second_combined_value, third_combined_value, fourth_combined_register

    def combine_values(self):
        # Lesepfad unverändert: nutzt die eigenen (unveränderlichen)
        # Adressdaten der Instanz, delegiert an die statische Berechnung.
        return self._combine_values_for(self._idal, self._idb, self._tab, self._var)

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
