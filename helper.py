'''
  helper.py is part of knxadapter3.py
  Copyright (C) 2018-2021 Andreas Frisch <fraxinas@purplegecko.de>

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

import logging
from sys import stderr

logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s: %(message)s',
    stream=stderr,
)

knxalog = logging.getLogger(__name__)
def log_async_exception(fun):
    @wraps(fun)
    async def wrapper(*args, **kwargs):
        try:
            return await fun(*args, **kwargs)
        except:
            knxalog.exception("Exception in %r:", fun.__qualname__)
            raise
    return wrapper

def setLogLevel(v):
    levels = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}
    level = v in levels and levels[v] or logging.CRITICAL
    knxalog.setLevel(level)

class BasePlugin:
    def __init__(self, daemon, cfg):
            self.d = daemon
            self.cfg = cfg
            self.device_name = cfg["name"]
            self.client = None
            self.obj_list = []
            default_hysteresis = "default_hysteresis" in self.cfg and self.cfg["default_hysteresis"] or 0
            for obj in cfg["objects"]:
                if obj["enabled"]:
                    obj.update({"value": 0})
                    if not "hysteresis" in obj:
                        obj.update({"hysteresis": default_hysteresis})
                    self.obj_list.append(obj)

    def _run(self):
        pass

    def run(self):
        if self.cfg["enabled"]:
            runner = self._run()
            if runner:
                knxalog.info("running client for {}...".format(self.device_name))
                return runner

    def quit(self):
        if self.client:
            knxalog.info("quit client for {}...".format(self.device_name))
            self.client.close()

    def get_obj_by_knxgrp(self, knx_group):
        return next(item for item in self.obj_list if item["knx_group"] == knx_group)
