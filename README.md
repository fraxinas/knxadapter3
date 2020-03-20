knxadapter3

(CC) 2020 by Andreas Frisch <fraxinas@schaffenburg.org>

This python3 asyncio script opens a local HTTP server to which LAN-enabled 
weather stations like WH2601 can push their data instead of wunderground.
Weatherd3 then takes the data, converts units where needed and relays
it to a linknx server under the configured group addresses.

In the weather logger's web interface, please configure:
Remote Server: Customized
Server IP: IP of the machine running `knxadapter3`
Server Port: 8084 by default
Server Type: PHP
Station ID / Password: anything (ignored)

`knxadapter3.py` can poll the info from a APCUPSD to reflect the status of
an APC Universal Power Supply to the KNX Bus.

This script also works as a bridge between KNX and a Pioneer AVR with
telnet such as a VSX-2020.

`knxadapter3.py` requires `python3` with `asyncio` and `aiohttp`

please `cp config_sample.json config.json` and set the correct
`linknx host` and `knx_group` addresses.

Usage: `knxadapter3.py [config-file]`
