'''
  apc_ups.py is part of knxadapter3.py
  Copyright (C) 2020 Andreas Frisch <fraxinas@purplegecko.de>

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
import re
from helper import BasePlugin, knxalog as log

def plugin_def():
    return ApcUps

class ApcUps(BasePlugin):
    def __init__(self, daemon, cfg):
        super(ApcUps, self).__init__(daemon, cfg)
        self.ups_reader = None
        self.ups_writer = None
        self.expression = ".*?"
        for obj in self.obj_list:
            ups_expr = obj["ups_expr"]
            self.expression += ups_expr + '.*?'
            group = obj["knx_group"]
        self.poll_interval = "poll_interval" in cfg and cfg["poll_interval"] or 10

    async def ups_client(self, loop):
        self.ups_reader, self.ups_writer = await asyncio.open_connection(
            self.cfg["host"], self.cfg["port"], loop=loop)

    async def poll_ups(self):
        while True:
            hello = (chr(0)+chr(6)+"status").encode('ascii')
            log.debug("{} polling APCD: {!r}".format(self.device_name, hello))
            self.ups_writer.write(hello)
            await self.ups_writer.drain()
            await asyncio.sleep(self.poll_interval)

    async def handle_ups(self):
        while True:
            data = await self.ups_reader.readuntil(b'\x00\x00')
            debug_msg = []

            if not data:
                break

            data = data.decode('ascii')
            m = re.match(self.expression, data, re.DOTALL)

            if m:
                group_value_dict = {}
                for idx, o in enumerate(self.obj_list):
                    group = o["knx_group"]
                    val = m.groups(0)[idx]
                    debug_line = "idx: {} group: {} val: {}".format(idx, group, val)
                    prev_val = o["value"]
                    try:
                        value = float(val)
                        debug_line += " numeric value: {0:g}".format(value)
                        hysteresis = o["hysteresis"]
                        if type(hysteresis) == str and "%" in hysteresis and abs(value - prev_val) <= float(hysteresis.strip('%'))*value*0.01 or type(hysteresis) == float and abs(value - prev_val) <= hysteresis:
                            debug_msg.append("{}-{:g} < {:g} hysteresis, ignored!".format(debug_line, prev_val, hysteresis))
                            continue
                        elif prev_val == value:
                            debug_msg.append("{} unchanged, ignored!".format(debug_line))
                            continue
                        group_value_dict[group] = "%.2f" % value

                    except ValueError:
                        if val == "ONLINE":
                            value = "true"
                        elif val == "ONBATT":
                            value = "false"
                        debug_line += " non-numeric value: ->{}".format(value)
                        if prev_val == value:
                            debug_msg.append("{} unchanged, ignored!".format(debug_line))
                            continue
                        group_value_dict[group] = value

                    o["value"] = value
                    debug_msg.append(debug_line)

                log.debug("{} {!r}\t".format(self.device_name, data)+"\n\t".join(debug_msg))

                if group_value_dict:
                    await self.d.set_group_value_dict(group_value_dict)

            else:
                log.warning("{} Couldn't parse {!r}".format(self.device_name, data))

    def _run(self):
        self.client = self.d.loop.run_until_complete(self.ups_client(self.d.loop))
        poll_task = self.d.loop.create_task(self.poll_ups())
        return [self.handle_ups(), poll_task]
