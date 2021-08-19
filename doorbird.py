'''
  doorbird.py is part of knxadapter3.py
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
from aiohttp import web
from helper import BasePlugin, knxalog as log

def plugin_def():
    return Doorbird

class Doorbird(BasePlugin):
    def __init__(self, daemon, cfg):
        super(Doorbird, self).__init__(daemon, cfg)
        daemon.value_direct_cbs.append(self.process_direct)
        self.doorbird_app = None
        self.doorbird_handler = None
        self.doorbird_server = None

    async def handle(self, request):
        query = request.rel_url.query
        log.debug(f"{self.device_name} handle: {query!r}")
        if "toggle" in query:
            if not "key" in query:
                log.warning(f"{self.device_name} no FOB key given when handling {query!r}!")
                return web.Response(status=403, text="Forbidden\n")
            fobkey = query["key"]
            fobname = self.d.cfg["fobs"].get(fobkey, "unknown")
            for item in self.obj_list:
                if "opener" in item:
                    opener = item
                if "lock" in item:
                    lock = item
            if lock["value"] == "close":
                if fobkey in lock["allowed_fobs"]:
                    log.warning(f"{self.device_name} {fobname}' FOB ({fobkey}) validated for unlocking!")
                    await self.d.set_group_value_dict({lock["knx_group"]:"open"})
                    lockdelay = lock["delay"]
                    await asyncio.sleep(lock["delay"])
                    log.warning(f"{self.device_name} lockdelay waited for {lockdelay}s")
                else:
                    log.warning(f"{self.device_name} {fobname}' FOB ({fobkey}) not allowed to unlock!")
                    return web.Response(status=403, text="Forbidden\n")
            if fobkey in opener["allowed_fobs"]:
                log.info(f"{self.device_name} {fobname}'s FOB validated ({fobkey}) for opening!")
                await self.d.set_group_value_dict({opener["knx_group"]:"on"})
                await asyncio.sleep(opener["delay"])
                await self.d.set_group_value_dict({opener["knx_group"]:"off"})
                return web.Response(text="success\n")
            else:
                log.warning(f"{self.device_name} {fobname}'s FOB ({fobkey}) not allowed to open!")
                return web.Response(status=403, text="Forbidden\n")
        return web.Response(status=404, text="Not found\n")

    async def process_direct(self, knx_group, value):
        try:
            o = self.get_obj_by_knxgrp(knx_group)
            log.debug(f"{self.device_name} update internal state knx_group={knx_group} value={value}")
            o["value"] = value
        except StopIteration:
            return

    def run(self):
        if self.cfg["enabled"]:
            self.doorbird_app = web.Application(debug=True)
            self.doorbird_app.router.add_get('/doorbird/{name}', self.handle)
            self.doorbird_handler = self.doorbird_app.make_handler()
            log.info(f"{self.device_name} running doorbird endpoint...")
            doorbird_coro = self.d.loop.create_server(self.doorbird_handler, self.d.cfg["sys"]["listenHost"], self.cfg["listenPort"])
            self.doorbird_server = self.d.loop.run_until_complete(doorbird_coro)
            return None

    def quit(self):
        if self.doorbird_server:
            log.info(f"{self.device_name} quit doorbird endpoint...")
            self.doorbird_server.close()
            self.d.loop.run_until_complete(self.doorbird_app.shutdown())
            self.d.loop.run_until_complete(self.doorbird_handler.shutdown(2.0))
            self.d.loop.run_until_complete(self.doorbird_app.cleanup())
