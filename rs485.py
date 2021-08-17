'''
  rs485.py is part of knxadapter3.py
  Copyright (C) 2021 Andreas Frisch <fraxinas@purplegecko.de>

  This program is free software; you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation; either version 2 of the License, or (at
  your option) any later version.

  This program is distributed in the hope that it will be useful, but
  WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
  General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program; if not, write to the Free Software
  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
  USA.
'''

import asyncio
import logging
from helper import BasePlugin, knxalog as log
import serial_asyncio
from serial.serialutil import SerialException

def plugin_def():
    return RS485

class RS485(BasePlugin):
    def __init__(self, daemon, cfg):
        super(RS485, self).__init__(daemon, cfg)
        daemon.knx_read_cbs.append(self.process_knx)
        daemon.value_direct_cbs.append(self.process_direct)
        log.debug("{} obj_list: {!r}".format(self.device_name, self.obj_list))
        self._reader = None
        self._writer = None

    async def rs485_connection(self, loop):
        baudrate = "baudRate" in self.cfg and self.cfg["baudRate"] or 115200
        dev = self.cfg["serialDevice"]
        try:
            self._reader, self._writer = await serial_asyncio.open_serial_connection(loop=loop, url=dev, baudrate=baudrate)
            log.info(f"{self.device_name} Successfully opened {dev} @ {baudrate} baud.")
        except SerialException as e:
            log.error(f"{self.device_name} Can't open {dev}. {e!r}")

    async def handle_rs485(self):
        while True:
            try:
                line = await self._reader.readline()
                cmd = line.decode('utf-8').strip()
                log.debug(self.device_name+" received: '"+cmd+"'")
                (key, val) = cmd.split('=')

                o = self._get_obj_by_key(key)
                if "receive" in o["enabled"]:
                    if "valmap" in o and val in o["valmap"]:
                        knxval = o["valmap"][val]
                    else:
                        knxval = val
                    await self.d.set_group_value_dict({o["knx_group"]: knxval})
                else:
                    log.warning(f"{self.device_name} command key {key} is not a receiving object!")

            except ValueError:
                log.warning("{} couldn't parse command {!r}!".format(self.device_name, line))
            except StopIteration:
                log.warning(f"{self.device_name} command key {key} not configured!")

    def _get_obj_by_key(self, rs485key):
        return next(item for item in self.obj_list if item["rs485key"] == rs485key)

    async def process_direct(self, knx_group, knx_val):
        try:
            o = self.get_obj_by_knxgrp(knx_group)
            if "send" in o["enabled"]:
                debug_msg = f"{self.device_name} process_direct({knx_group}={knx_val})"
                await self.write_rs485(o, knx_val, debug_msg)
        except StopIteration:
            return

    async def process_knx(self, cmd):
        try:
            knx_group, knx_val = cmd.split("=")
            try:
                o = self.get_obj_by_knxgrp(knx_group)
                if "send" in o["enabled"]:
                    debug_msg = f"{self.device_name} process_knx({knx_group}={knx_val})"
                    await self.write_rs485(o, knx_val, debug_msg)
            except StopIteration:
                pass
            return True
        except:
            return False

    async def write_rs485(self, o, value, debug_msg):
        rs485key = o["rs485key"]
        if "valmap" in o:
            val = next((key for key, val in o["valmap"].items() if val == value), value)
        else:
            val = value
        cmd = (rs485key+'='+val)
        log.debug(f"{debug_msg} writing RS485 command {cmd}")
        self._writer.write((cmd+'\r\n').encode(encoding='ascii'))
        await self._writer.drain()

    def _run(self):
        self._client = self.d.loop.run_until_complete(self.rs485_connection(self.d.loop))
        if self._reader and self._writer:
            return [self.handle_rs485()]
        else:
            return False
