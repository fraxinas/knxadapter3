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

def plugin_def():
    return RS485

class RS485(BasePlugin):
    def __init__(self, daemon, cfg):
        super(RS485, self).__init__(daemon, cfg)
        daemon.knx_read_cbs.append(self.process_knx)
        daemon.value_direct_cbs.append(self.process_direct)
        log.debug("{} obj_list: {!r}".format(self.device_name, self.obj_list))

    async def rs485_connection(self, loop):
        baudrate = "baudRate" in self.cfg and self.cfg["baudRate"] or 115200
        self._reader, self._writer = await serial_asyncio.open_serial_connection(loop=loop, url=self.cfg["serialDevice"], baudrate=baudrate)

    async def handle_rs485(self):
        log_msg = []
        while True:
            try:
                line = await self._reader.readline()
                line = str(line, 'utf-8')
                log.debug(self.device_name+" received: '"+line+"'")

                (key, val) = line.strip().split('=')

                o = self._get_obj_by_key(key)
                if o and "receive" in o["enabled"]:
                    if "valmap" in o and val in o["valmap"]:
                        knxval = o["valmap"][val]
                    else:
                        knxval = val
                    await self.d.set_group_value_dict({o["knx_group"]: knxval})
                else:
                    log.warning("{} command key {} not configured!".format(self.device_name, key))

            except ValueError:
                log.warning("{} couldn't parse command {!r}!".format(self.device_name, line))

    def _get_obj_by_key(self, rs485key):
        return next(item for item in self.obj_list if item["rs485key"] == rs485key)

    async def process_direct(self, group, value):
        try:
            o = self.get_obj_by_knxgrp(group)
            if "send" in o["enabled"]:
                await self.write_rs485(o, value)
        except StopIteration:
            return

    async def process_knx(self, cmd):
        try:
            knx_grp, raw = cmd.split("=")
            log.debug(f"{self.device_name} knx group {knx_grp} raw={raw}")
            try:
                o = self.get_obj_by_knxgrp(knx_grp)
                if "send" in o["enabled"]:
                    await self.write_rs485(o, raw)
            except StopIteration:
                return True
        except:
            return False

    async def write_rs485(self, o, value):
        rs485key = o["rs485key"]
        if "valmap" in o:
            val = next((key for key, val in o["valmap"].items() if val == value), value)
        else:
            val = value
        cmd = (rs485key+'='+val)
        log.debug(f"{self.device_name} writing RS485 command {cmd}")
        self._writer.write((cmd+'\r\n').encode(encoding='ascii'))
        self._writer.drain()

    def _run(self):
        self._client = self.d.loop.run_until_complete(self.rs485_connection(self.d.loop))
        return [self.handle_rs485()]
