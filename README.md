# knxadapter3

(CC) 2020 by Andreas Frisch <fraxinas@purplegecko.de>

## OwO what's this?
**`knxadapter3.py` is a universal extensible protocol converter for LinKNX.**
It uses python3 asyncio to collect data from the configured devices and hand them over to LinKNX to make them available on the KNX bus and log the values under the configured group addresses. For each measurement object, a relative or absolute hysteresis can be specified to ease bus traffic.

Currently it consists of the following

## Plugins
### weather_station
* opens a local HTTP server to which LAN-enabled
weather stations like WH2601 can push their data instead of wunderground.
* it then extracts the values from the HTTP query, converts units where needed and relays them to LinKNX
* In the weather logger's web interface, please configure:
```
Remote Server: Customized
Server IP: IP of the machine running `knxadapter3`
Server Port: 8084 by default
Server Type: PHP
Station ID / Password: anything (will be ignored)
```

### apc_ups
* can poll the info from an `APCUPSD` to reflect the status of
an APC Universal Power Supply to the KNX Bus

### pioneer_avr
* this plugin works as a bidirectional bridge between KNX and older Pioneer AVRs with telnet such as a VSX-2020

### onkyo_avr
* replacement for the `pioneer_avr` plugin, for newer Onkyo and Pioneer AVRs such as VSX-LX305

### modbus_device
* can query registers from Modbus-TCP enabled devices such as smart meters and solar inverters

### mqtt
* generic MQTT client supporting subscription and publishing of MQTT topics

### daikin_ac
* wrapper for `daikinapi` Air Conditionings

### rfid
* plugin for reading 125 kHz RFID FOBs or cards using an RDM6300 module

## prerequisites
### dependencies
* `knxadapter3.py` requires `python3` with `asyncio` + `importlib`
Additonal dependencies:

| plugin(s)       | module          |
| :-------------- | :-------------- |
| `apc_ups`       | `re`            |
| `modbus_device` | `pymodbus`      |
| `mqtt`          | `asyncio_mqtt`  |
| `weather_station` & `doorbird` | `aiohttp`  |
| `rfid`          | `rdm6300`       |
| `RS485`         | `pyserial-asyncio` |
| `onkyo_avr`     | `onkyo-eiscp`   |

* install these dependencies using `pip install`

### configuration
* please `cp config_sample.json config.json` and set the respective properties, should be self-explanatory

## LinKNX integration
In order to send data from LinKNX to AC, AVR or MQTT devices, it is necessary to create respective rules which transmit the group address and value to knxadapter3 when changed. The rules should look like this:
```
	<rule id="mqtt_topic1_changed" init="false">
		<condition type="object" id="sensors:mqtt:topic1" trigger="true"/>
		<actionlist type="if-true">
			<action type="script">
				local socket = require("socket")
				client = socket.tcp();
				client:connect("knxadapter-host", 8103);
				msg = "sensors:mqtt:topic1=" .. obj("sensors:mqtt:topic1");
				client:send(msg);
				client:close();
			</action>
		</actionlist>
	</rule>
```

## Usage
$ `knxadapter3.py [config-file]`
