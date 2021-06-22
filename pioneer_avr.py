'''
  pioneer_avr.py is part of knxadapter3.py
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
from helper import BasePlugin, knxalog as log

def plugin_def():
    return PioneerAVR

class PioneerAVR(BasePlugin):
    def __init__(self, daemon, cfg):
        super(PioneerAVR, self).__init__(daemon, cfg)
        self.avr_reader = None
        self.avr_writer = None
        self.accu_word = None
        daemon.knx_read_cbs.append(self.process_knx)
        log.debug("{} obj_list: {!r}".format(self.device_name, self.obj_list))

    async def avr_client(self, loop):
        self.avr_reader, self.avr_writer = await asyncio.open_connection(
            self.cfg["host"], self.cfg["port"], loop=loop)

    async def send_avr(self, data):
        log.debug("sending to avr: '%s'" % data)
        self.avr_writer.write((data+'\r').encode(encoding='ascii'))
        self.avr_writer.drain()

    def get_value_by_avr(self, avr_object):
        return next(item for item in self.obj_list if item["avr_object"] == avr_object)["value"]

    def get_knx_by_avr(self, avr_object):
        return next(item for item in self.obj_list if item["avr_object"] == avr_object)["knx_group"]

    def set_value_for_avr(self, avr_object, value):
        next(item for item in self.obj_list if item["avr_object"] == avr_object)["value"] = value

    async def process_knx(self, cmd):
        msg = None
        log.debug("avr processes knx command '%r'" % cmd)
        try:
            if cmd[0] == 'P':
                if cmd[1:3] == "on" and self.get_value_by_avr("power") != "on":
                    msg = "PO"
                elif cmd[1:4] == "off" and self.get_value_by_avr("power") != "off":
                    msg = "PF"
            elif cmd[0] == 'V':
                new_vol = int(cmd[1:])
                if new_vol != self.get_value_by_avr("volume"):
                    avr_vol = round(new_vol * (185.0 / 255.0))
                    msg = "%03dVL" % avr_vol
                    set_value_for_avr("volume", new_vol)
            elif cmd[0] == 'F':
                new_fn = int(cmd[1:3])
                if new_fn in range (0,32) and new_fn != self.get_value_by_avr("fn"):
                    msg = "%02dFN" % new_fn
                    set_value_for_avr("fn", new_fn)
            if msg:
                await self.send_avr(msg)
        except:
            log.error("Couldn't parse linknx command: {!r}".format(cmd))

    async def handle_avr(self):
        while True:
            sequence = None
            data = await self.avr_reader.readline()

            if not data:
                break

            line = data.decode('ascii')
            log.debug('avr received {!r}'.format(line))

            if line.startswith('FL02'):
              if line == "FL022020202020202020202020202020\r\n":
                self.accu_word = self.accu_word and self.accu_word.rstrip() or ""
                self.set_value_for_avr("display_text", self.accu_word)
                sequence = '<object id="%s" value="%s"/>' % (self.get_knx_by_avr("display_text"), self.get_value_by_avr("display_text"))
                log.debug("display_text complete! '%s'" % self.get_value_by_avr("display_text"))
              else:
                new_word = bytes.fromhex(line[4:-2]).decode('iso8859_15')
                if self.accu_word == None:
                    self.accu_word = new_word
                    log.debug("1START new_word={!r} accu_word={!r}".format(new_word, self.accu_word))
                elif self.accu_word[-13:] != new_word[:-1]:
                    if not self.get_value_by_avr("display_text") or new_word not in self.get_value_by_avr("display_text"):
                        self.set_value_for_avr("display_text", None)
                        self.accu_word = new_word
                        sequence = '<object id="%s" value="%s"/>' % (self.get_knx_by_avr("display_text"), self.accu_word)
                        log.debug("CHANGE new_word={!r} accu_word={!r} {}".format(new_word, self.accu_word, sequence))
                    else:
                        log.debug("STARTOVER new_word={!r} accu_word={!r}".format(new_word, self.accu_word))
                else:
                  self.accu_word += new_word[-1:]
                  log.debug("+++++ new_word={!r} accu_word={!r}".format(new_word, self.accu_word))
                if not self.get_value_by_avr("display_text") and self.accu_word[-1] != ' ':
                  sequence = '<object id="%s" value="%s"/>' % (self.get_knx_by_avr("display_text"), self.accu_word.rstrip())
                  log.debug("COMMIT new_word={!r} accu_word={!r} {}".format(new_word, self.accu_word, sequence))

            elif line.startswith('VOL'):
              avr_volume = int(line[3:])
              new_volume = round(avr_volume * (255.0 / 185.0))
              if new_volume != self.get_value_by_avr("volume"):
                self.set_value_for_avr("volume", new_volume)
                sequence = '<object id="%s" value="%d"/>' % (self.get_knx_by_avr("volume"), self.get_value_by_avr("volume"))

            elif line.startswith('PWR'):
              if line[3] == '0':
                self.set_value_for_avr("power", "on")
              else:
                self.set_value_for_avr("power", "off")
              sequence = '<object id="%s" value="%s"/>' % (self.get_knx_by_avr("power"), self.get_value_by_avr("power"))
              self.set_value_for_avr("display_text", None)
              sequence += '<object id="%s" value="%s"/>' % (self.get_knx_by_avr("display_text"), self.get_value_by_avr("display_text"))

            elif line.startswith('FN'):
              new_fn = int(line[2:4])
              if new_fn != self.get_value_by_avr("fn"):
                self.set_value_for_avr("fn", new_fn)
                sequence = '<object id="%s" value="%d"/>' % (self.get_knx_by_avr("fn"), self.get_value_by_avr("fn"))
                self.set_value_for_avr("display_text", None)
                sequence += '<object id="%s" value="%s"/>' % (self.get_knx_by_avr("display_text"), self.get_value_by_avr("display_text"))

            if sequence:
              await self.d.send_knx(sequence)

    def _run(self):
        self.client = self.d.loop.run_until_complete(self.avr_client(self.d.loop))
        return [self.handle_avr()]
