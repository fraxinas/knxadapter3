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

from aiohttp import web
from helper import BasePlugin, knxalog as log

def plugin_def():
    return Doorbird

class Doorbird(BasePlugin):
    def __init__(self, daemon, cfg):
        super(Doorbird, self).__init__(daemon, cfg)
        self.doorbird_app = None
        self.doorbird_handler = None
        self.doorbird_server = None

    async def handle(self, request):
        log.debug("handle: {!r}".format(request.rel_url.query))
        return web.Response(text="success\n")

    def run(self):
        if self.cfg["enabled"]:
            self.doorbird_app = web.Application(debug=True)
            self.doorbird_app.router.add_get('/doorbird/{name}', self.handle)
            self.doorbird_handler = self.doorbird_app.make_handler()
            log.info("running doorbird endpoint...")
            doorbird_coro = self.d.loop.create_server(self.doorbird_handler, self.d.cfg["sys"]["listenHost"], self.cfg["listenPort"])
            self.doorbird_server = self.d.loop.run_until_complete(doorbird_coro)
            return None

    def quit(self):
        if self.doorbird_server:
            log.info("quit doorbird endpoint...")
            self.doorbird_server.close()
            self.d.loop.run_until_complete(self.doorbird_app.shutdown())
            self.d.loop.run_until_complete(self.doorbird_handler.shutdown(2.0))
            self.d.loop.run_until_complete(self.doorbird_app.cleanup())
