'''
  weather_station.py is part of knxadapter3.py
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

from aiohttp import web
from helper import BasePlugin, knxalog as log

def plugin_def():
    return WeatherStation

class WeatherStation(BasePlugin):
    Unit_converter = {
        "mph_to_kmh": lambda v: (v*1.60934),
        "F_to_C": lambda t: ((t-32) / 1.8),
        "inch_to_mm": lambda h: (h*25.4),
        "inHg_to_hPa": lambda h: (h*33.8637526)
    }

    def __init__(self, daemon, cfg):
        super(WeatherStation, self).__init__(daemon, cfg)
        self.ws_app = None
        self.ws_handler = None
        self.ws_server = None

    async def process_values(self, query):
        group_value_dict = {}
        for obj in self.obj_list:
            sensor = obj["sensor"]
            group = obj["knx_group"]
            debug_msg = "%s->%s" % (sensor, group)

            if sensor in query and obj["enabled"]:
                try:
                    value = float(query[sensor])
                    if value == -9999:
                        log.debug("bogus value for {}, ignored!".format(debug_msg))
                        continue
                    debug_msg += " numeric value: {0:g}".format(value)
                    conversion = obj["conversion"]
                    if conversion and conversion in self.Unit_converter:
                        value = round(self.Unit_converter[conversion](value), 2)
                        debug_msg += "^={0:g}".format(value)

                    hysteresis = obj["hysteresis"]
                    prev_val = obj["value"]
                    if type(hysteresis) == str and "%" in hysteresis and abs(value - prev_val) <= float(hysteresis.strip('%'))*value*0.01 or type(hysteresis) == float and abs(value - prev_val) <= hysteresis:
                            log.debug("{0}-{1:g} < {2:g} hysteresis, ignored!".
                                    format(debug_msg, prev_val, hysteresis))
                            continue
                    elif prev_val == value:
                        log.debug("{!r} unchanged, ignored!".format(debug_msg))
                        continue
                    group_value_dict[group] = "%.2f" % value

                except ValueError:
                    value = query[sensor]
                    debug_msg += " non-numeric value:", value
                    if group in self.previous_values and value == self.previous_values[group]:
                        log.debug("{!r} unchanged, ignored!".format(debug_msg))
                        continue
                    group_value_dict[group] = value

                obj["value"] = value
                log.debug(debug_msg)

        if group_value_dict:
            await self.d.set_group_value_dict(group_value_dict)

    async def handle(self, request):
        log.debug("handle: {!r}".format(request.rel_url.query))
        await self.process_values(request.rel_url.query)
        return web.Response(text="success\n")

    def run(self):
        if self.cfg["enabled"]:
            self.ws_app = web.Application(debug=True)
            self.ws_app.router.add_get('/weatherstation/{name}', self.handle)
            self.ws_handler = self.ws_app.make_handler()
            log.info("running weather station receiver...")
            ws_coro = self.d.loop.create_server(self.ws_handler, self.d.cfg["sys"]["listenHost"], self.cfg["listenPort"])
            self.ws_server = self.d.loop.run_until_complete(ws_coro)
            return None

    def quit(self):
        if self.ws_server:
            log.info("quit weather station receiver...")
            self.ws_server.close()
            self.d.loop.run_until_complete(self.ws_app.shutdown())
            self.d.loop.run_until_complete(self.ws_handler.shutdown(2.0))
            self.d.loop.run_until_complete(self.ws_app.cleanup())
