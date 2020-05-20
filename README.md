# knxadapter3

(CC) 2020 by Andreas Frisch <fraxinas@schaffenburg.org>

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
* this plugin works as a bidirectional bridge between KNX and a Pioneer AVR with telnet such as a VSX-2020.

### modbus_device
* can query registers from Modbus-TCP enabled devices such as smart meters and solar inverters

## prerequisites
* `knxadapter3.py` requires `python3` with `asyncio` and `aiohttp`
* additonally `re` for `apc_ups` and `pymodbus` for `modbus_device`
* please `cp config_sample.json config.json` and set the respective
properties, should be self-explanatory

## Usage
$ `knxadapter3.py [config-file]`
