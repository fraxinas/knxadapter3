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
import rdm6300
import asyncio
from helper import BasePlugin, knxalog as log

def plugin_def():
    return RFID

class Rdm6300Reader(rdm6300.BaseReader):
    def __init__(self, cfg, daemon):
        super(Rdm6300Reader, self).__init__(cfg["serialDevice"])
        self.d = daemon
        self.device_name = cfg["name"]
        self.fobs = daemon.cfg["fobs"]
        self.forbidden_fobs = daemon.cfg["forbidden_fobs"]
        self.throttle_delay = "throttle_delay" in cfg and cfg("throttle_delay") or 5
        self.objs_by_fob = {}
        for o in cfg["objects"]:
            for key in o["allowed_fobs"]:
                if o["enabled"]:
                    if key not in self.objs_by_fob:
                        self.objs_by_fob[key] = []
                    d = {"knx_group": o["knx_group"], "delay": o["delay"]}
                    self.objs_by_fob[key].append(d)
        log.debug(f"objs_by_fob: {self.objs_by_fob!r}")

    def card_inserted(self, card):
        asyncio.run_coroutine_threadsafe(self._card_inserted(card), self.d.loop).result()

    def card_removed(self, card):
        asyncio.run_coroutine_threadsafe(self._card_removed(card), self.d.loop).result()

    def invalid_card(self, card):
        asyncio.run_coroutine_threadsafe(self._invalid_card(card), self.d.loop).result()

    async def _card_inserted(self, card):
        key = str(card.value)
        if key in self.forbidden_fobs:
            name = self.fobs[key]
            log.warning(f"{name}'s FOB forbidden attempt! ({card})")

        if key in self.fobs:
            name = self.fobs[key]
            log.info(f"{name}'s FOB validated ({card})")
            if key in self.objs_by_fob:
                for obj in self.objs_by_fob[key]:
                    knx_group = obj["knx_group"]
                    log.info(f"opening {knx_group}")
                    await self.d.set_group_value_dict({knx_group: "on"})
            else:
                log.warning(f"{name}'s FOB forbidden attempt! ({card})")
        else:
            log.warning(f"Unknown FOB {card} attempted! delaying for {self.throttle_delay} s!")
            await asyncio.sleep(self.throttle_delay)

    async def _card_removed(self, card):
        log.debug(f"FOB {card} removed!")
        key = str(card.value)
        if key in self.objs_by_fob:
            for obj in self.objs_by_fob[key]:
                knx_group = obj["knx_group"]
                delay = obj["delay"]
                await asyncio.sleep(delay)
                log.debug(f"stopping {knx_group}")
                await self.d.set_group_value_dict({knx_group: "off"})

    async def _invalid_card(self, card):
        log.warning(f"Invalid FOB {card} attempted!")

class RFID(BasePlugin):
    def __init__(self, daemon, cfg):
        super(RFID, self).__init__(daemon, cfg)
        log.debug(f"{self.device_name}")
        self.reader = None

    def _run(self):
        self.reader = Rdm6300Reader(self.cfg, self.d)
        rfid_task = self.d.loop.run_in_executor(None, self.reader.start)
        return [rfid_task]
