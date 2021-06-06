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
    def card_inserted(self, card):
        print(f"card inserted {card}")

    def card_removed(self, card):
        print(f"card removed {card}")

    def invalid_card(self, card):
        print(f"invalid card {card}")

class RFID(BasePlugin):
    def __init__(self, daemon, cfg):
        super(RFID, self).__init__(daemon, cfg)
        self.reader = None

    def _run(self):
        self.reader = Rdm6300Reader(self.cfg["serialDevice"])
        rfid_task = self.d.loop.run_in_executor(None, self.reader.start)
        return [rfid_task]
      
