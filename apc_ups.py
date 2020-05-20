'''
  apc_ups.py is part of knxadapter3.py
  Copyright (C) 2020 Andreas Frisch <fraxinas@schaffenburg.org>

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

    async def ups_client(self, loop):
        self.ups_reader, self.ups_writer = await asyncio.open_connection(
            self.cfg["host"], self.cfg["port"], loop=loop)

    async def poll_ups(self):
        while True:
            hello = (chr(0)+chr(6)+"status").encode('ascii')
            print ("polling ups", hello)
            self.ups_writer.write(hello)
            await self.ups_writer.drain()
            await asyncio.sleep(10)

    async def handle_ups(self):
        log.debug('handle_ups...')
        while True:
            data = await self.ups_reader.readuntil(b'\x00\x00')
            log.debug('ups received {!r}'.format(data))

            if not data:
                break
            
            data = data.decode('ascii')

            log.debug('received apcups data {!r}'.format(data))

            m = re.match(self.expression, data, re.DOTALL)
            log.debug("match: "+str(m))

            if m:
                print(m.groups())
                sequence = ""
                
                for idx, o in enumerate(self.obj_list):
                    group = o["knx_group"]
                    val = m.groups(0)[idx]
                    debug_msg = "idx: {0} group: {1} val: {2}".format(idx, group, val)
                    prev_val = o["value"]
                    try:
                        value = float(val)
                        debug_msg += " numeric value: {0:g}".format(value)
                        hysteresis = o["hysteresis"]
                        if type(hysteresis) == str and "%" in hysteresis and abs(value - prev_val) <= float(hysteresis.strip('%'))*value*0.01 or type(hysteresis) == float and abs(value - prev_val) <= hysteresis:
                            log.debug("{0} {1}-{2:g} < {3:g} hysteresis, ignored!".
                                format(group, value, prev_val, hysteresis))
                            continue
                        elif prev_val == value:
                            log.debug("{!r} unchanged, ignored!".format(debug_msg))
                            continue
                        sequence += '<object id="%s" value="%.2f"/>' % (group, value)
                    
                    except ValueError:
                        if val == "ONLINE":
                            value = "true"
                        elif val == "ONBATT":
                            value = "false"
                        debug_msg += " non-numeric value: {0}->{1}".format(val, value)
                        if prev_val == value:
                            log.debug("{!r} unchanged, ignored!".format(debug_msg))
                            continue
                        sequence += '<object id="%s" value="%s"/>' % (group, value)

                    o["value"] = value
                    log.debug(debug_msg)

                if sequence:
                    await self.d.send_knx(sequence)

    def _run(self):
        self.client = self.d.loop.run_until_complete(self.ups_client(self.d.loop))
        poll_task = self.d.loop.create_task(self.poll_ups())
        return [self.handle_ups(), poll_task]
