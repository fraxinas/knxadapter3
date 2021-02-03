#! /usr/bin/python3
# -*- coding: utf-8 -*-

'''
  knxadapter3.py
  Copyright (C) 2018,2020 Andreas Frisch <fraxinas@schaffenburg.org>

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

import sys
import json
import asyncio
from importlib import import_module
from helper import setLogLevel, knxalog as log

PLUGINS = ("apc_ups", "daikin_ac", "modbus_device", "mqtt", "pioneer_avr", "weather_station")

class KnxAdapter():
    def __init__(self, argv):
        if len(sys.argv) > 1 and sys.argv[1]:
            cfg_file = sys.argv[1]
        else:
            cfg_file = sys.path[0] + '/config.json'
        try:
            with open(cfg_file) as json_data_file:
                self.cfg = json.load(json_data_file)

        except FileNotFoundError:
            message = "Couldn't open the config file " + cfg_file
            log.error(message, sys.exc_info()[0])
            sys.exit(0)

        setLogLevel(self.cfg["sys"]["verbosity"])

        self.knx_client_reader = None
        self.knx_client_writer = None

        self._knx_lock = asyncio.Lock()

        self.loop = asyncio.get_event_loop()
        self.knx_read_cbs = []

    async def linknx_client(self, loop, knxcfg):
        self.knx_client_reader, self.knx_client_writer = await asyncio.open_connection(
            knxcfg["host"], knxcfg["port"])

    async def knx_server_handler(self, reader, writer):
        data = await reader.readline()
        cmd = data.decode()

        addr = writer.get_extra_info('peername')
        log.debug("Received %r from %r" % (cmd, addr))

        for callback in self.knx_read_cbs:
            await callback(cmd)

        writer.close()

    async def send_knx(self, sequence):
        async with self._knx_lock:
            xml = '<write>' + sequence + '</write>\n\x04'
            log.debug("sending to knx:{!r}".format(xml))
            self.knx_client_writer.write(xml.encode(encoding='utf_8'))
            self.knx_client_writer.drain()
            data = await asyncio.wait_for(self.knx_client_reader.readline(), timeout=30.0)
            decoded = data.decode()
            if "<write status='error'>" in decoded:
                log.error("LinKNX {}".format(decoded[1:-1]))
            else:
                log.debug("LinKNX {!r}".format(decoded))

    def start(self):
        log.info("Started KNX Bus Adapter Deamon.")

        knx_client = self.loop.run_until_complete(self.linknx_client(self.loop, self.cfg["linknx"]))

        knx_server_coro = asyncio.start_server(self.knx_server_handler, self.cfg["sys"]["listenHost"], self.cfg["linknx"]["listenPort"], loop=self.loop)
        knx_server = self.loop.run_until_complete(knx_server_coro)

        plugins = []
        for plugin_config in self.cfg["plugins"]:
            klass = plugin_config["class"]
            if klass in PLUGINS and plugin_config["enabled"]:
                try:
                    plugin_module = import_module(klass)
                    plugin_class = plugin_module.plugin_def()
                    if plugin_class:
                        plugins.append(plugin_class(self, plugin_config))
                except ModuleNotFoundError as e:
                    log.warning("module not found: {}. Plugin '{}' unavailable!".format(e, klass))

        tasks = []
        for plugin in plugins:
            task = plugin.run()
            if task:
                tasks += task

        futs = asyncio.gather(*tasks)
        self.loop.run_until_complete(futs)

        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            knx_server.close()
            self.loop.run_until_complete(knx_server.wait_closed())
            for plugin in plugins:
                plugin.quit()
            self.loop.close()

if __name__ == "__main__":
    knx_adapter = KnxAdapter(sys.argv[1:])
    knx_adapter.start()

