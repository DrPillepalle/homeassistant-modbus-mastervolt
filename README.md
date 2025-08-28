# Mastervolt Modbus Integration Module

This module integrates Mastervolt devices via Modbus. It has been tested with the Mastervolt MLI Ultra 12/5500, Mass Combi Pro 12/3000-150 230V, SCM60 MPPT-MB, MasterBus Modbus Interface, Mastervolt USB Interface. 

## How to Retrieve Necessary Parameters

For each value you need to read or write, you must obtain the `IDAL`, `IDB`, `TAB`, and `VAR` parameters from MasterAdjust (Windows App, free download from Mastervolt: https://www.mastervolt.de/downloads/so/)

### Steps to Retrieve Parameters:

1. **IDAL and IDB:**
   - Right-click on the device in MasterAdjust.
   - Select "Properties."
   - Note down the `IDAL` and `IDB` values.
   
2. **TAB:**
   - Use the following conventions:
     - `0` for Monitoring
     - `1` for Alarm
     - `2` for History
     - `3` for Configuration
   
3. **VAR:**
   - Hover the mouse over the desired value to obtain its Index.
   - This Index is in decimal format; convert it to hexadecimal before using it in the `configuration.yaml`.

## Modbus Connection Requirements

This module requires a Modbus connection. Ensure that it is enabled and that you set the correct values for `port`, `baudrate`, `stopbits`, `bytesize`, `parity`, and `timeout`.

**Note:** The Modbus module requires at least one sensor to function. A dummy sensor can be used if needed.

## Modbus Message Structure

The module generates a Modbus message in the following format:
Certainly! Here's the content formatted as a .md file:

md

# Mastervolt Modbus Integration Module

This module integrates Mastervolt devices via Modbus. It has been tested with the Mastervolt Combi Master and Mastershunt.

## How to Retrieve Necessary Parameters

For each value you need to read or write, you must obtain the `IDAL`, `IDB`, `TAB`, and `VAR` parameters from MasterAdjust.

### Steps to Retrieve Parameters:

1. **IDAL and IDB:**
   - Right-click on the device in MasterAdjust.
   - Select "Properties."
   - Note down the `IDAL` and `IDB` values.
   
2. **TAB:**
   - Use the following conventions:
     - `0` for Monitoring
     - `1` for Alarm
     - `2` for History
     - `3` for Configuration
   
3. **VAR:**
   - Hover the mouse over the desired value to obtain its Index.
   - This Index is in decimal format; convert it to hexadecimal before using it in the `configuration.yaml`.

## Modbus Connection Requirements

This module requires a Modbus connection. Ensure that it is enabled and that you set the correct values for `port`, `baudrate`, `stopbits`, `bytesize`, `parity`, and `timeout`.

**Note:** The Modbus module requires at least one sensor to function. A dummy sensor can be used if needed.

## Modbus Message Structure

The module generates a Modbus message in the following format:

0x01 0x17 0x00 0x00 0x00 0x06 0x00 0x00 0x00 0x06 0x0c 0x1b 0x02 0xc4 0xd9 0x00 0x00 0x00 0x08 0x00 0x00 0x80 0x3f 0xea 0xff

### Message Breakdown

<table>
  <tr>
    <th>Byte</th>
    <th>Value</th>
    <th>Description</th>
  </tr>
  <tr>
    <td>0x01</td>
    <td>Slave modbus id</td>
    <td> 1 byte [fixed]</td>
  </tr>
  <tr>
    <td>0x17</td>
    <td>Function code 23</td>
    <td> 1 byte [fixed]</td>
  </tr>
  <tr>
    <td>0x00</td>
    <td rowspan="2">Read Address</td>
    <td rowspan="2">2 bytes<br>[fixed]</td>
  </tr>
  <tr>
    <td>0x00</td>
  </tr>
  <tr>
    <td>0x00</td>
    <td rowspan="2">Q.ty to read </td>
    <td rowspan="2">2 bytes<br>[fixed]</td>
  </tr>
  <tr>
    <td>0x06</td>
  </tr>
  <tr>
    <td>0x00</td>
    <td>Write start address</td>
    <td>2 Bytes<br>0 - read<br>1 - write</td>
  </tr>
  <tr>
    <td>0x00</td>
    <td rowspan="2">Q.ty to write</td>
    <td rowspan="2">2 bytes <br>[fixed]</td>
  </tr>
  <tr>
    <td>0x06</td>
  </tr>
  <tr>
    <td>0x0c</td>
    <td>Write byte count</td>
    <td>1 byte<br>[fixed]</td>
  </tr>
  <tr>
    <td>0x1B</td>
    <td>IDAL</td>
    <td>1 byte</td>
  </tr>
  <tr>
    <td>0x02</td>
    <td rowspan="3">IDB</td>
    <td rowspan="3">3 bytes</td>
  </tr>
  <tr>
    <td>0xC4</td>
  </tr>
  <tr>
    <td>0xD9</td>
  </tr>
  <tr>
    <td>0x00</td>
    <td rowspan="2">TAB</td>
    <td rowspan="2">2 bytes</td>
  </tr>
  <tr>
    <td>0x00</td>
  </tr>
  <tr>
    <td>0x00</td>
    <td rowspan="2">VAR</td>
    <td rowspan="2">2 bytes</td>
  </tr>
  <tr>
    <td>0x08</td>
  </tr>
  <tr>
    <td>0x00</td>
    <td rowspan="4">Value IEE 754</td>
    <td rowspan="4">4 bytes</td>
  </tr>
  <tr>
    <td>0x00</td>
  </tr>
  <tr>
    <td>0x80</td>
  </tr>
  <tr>
    <td>0x3F</td>
  </tr>
  <tr>
    <td>0xEA</td>
    <td rowspan="2">CRC</td>
    <td rowspan="2">2 bytes <br> Calculate <br>from <br>Modbus</td>
  </tr>
  <tr>
    <td>0xFF</td>
  </tr>
</table>

## Configuration Steps

### Step 1: Configure Modbus in `configuration.yaml`

```
modbus:
  - name: "modbus_hub1"
    type: serial
    method: rtu
    port: "/dev/ttyUSB0"
    baudrate: 115200
    stopbits: 1
    bytesize: 8
    parity: "E"
    timeout: 2
    sensors:
      - name: "Dummy"
        unit_of_measurement: "°C"
        address: 19
        input_type: holding
        scan_interval: 10000
        data_type: int16
        precision: 2
        slave: 1
```
###Step 2: Add Sensor for Reading

```
sensor:
  - platform: modbus_mastervolt
    name: "AC Main Voltage"
    idal: 0x1B
    idb: 0x02C4D9
    tab: 0x0000
    var: 0x0008
    scan_interval: 60 # seconds
    unit_of_measurement: "V"

    scan_interval: Set the interval (in seconds) for device scanning.
    unit_of_measurement: Specify the unit of measurement.
```

### Step 3: Add Sensor for Writing

```
sensor:
  ...
  - platform: modbus_mastervolt
    name: "InverterONOFF"
    idal: 0x1B
    idb: 0x02C4D9
    tab: 0x0000
    var: 0x0014
    rw: 1
    #value: 0 - 1
  ...
```
    Set rw to 1 for writing.

### Executing the Write

To perform the write operation, create a Home Assistant script:

```
action: modbus_mastervolt.send_command
data:
  command_name: InverterONOFF
  value: 1
alias: InverterONOFF
```

### Notes

The Modbus name must be modbus_hub1.

During startup, you may encounter errors such as:

```
Pymodbus: modbus_hub1: Error: device: 1 address: 19 -> pymodbus returned isError True
```

```
One or more parameters are missing from the configuration: idal=None, idb=None, tab=None, var=None
```

```
Failed to load integration: modbus_mastervolt
```

These errors are normal and typically occur due to the application load when configuration.yaml is not fully ready.
