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
from helper import BasePlugin, knxalog as log

def plugin_def():
    return RFID

class Rdm6300Reader(rdm6300.BaseReader):
    def __init__(self, cfg):
        super(Rdm6300Reader, self).__init__(cfg["serialDevice"])
        self.fobs = cfg["fobs"]

    def card_inserted(self, card):
        key = str(card.value)
        if key in self.fobs:
            val = self.fobs[key]
            name = val[0]
            allowed = val[1]
            if allowed:
                log.info(f"{name}'s FOB validated ({card})")
            else:
                log.warning(f"{name}'s FOB forbidden attempt! ({card})")
        else:
            log.warning(f"Unknown FOB {card} attempted!")

    def card_removed(self, card):
        log.debug(f"FOB {card} removed!")

    def invalid_card(self, card):
        log.warning(f"Invalid FOB {card} attempted!")

class RFID(BasePlugin):
    def __init__(self, daemon, cfg):
        super(RFID, self).__init__(daemon, cfg)
        self.reader = None

    def _run(self):
        self.reader = Rdm6300Reader(self.cfg)
        rfid_task = self.d.loop.run_in_executor(None, self.reader.start)
        return [rfid_task]
