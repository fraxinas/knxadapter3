'''
  onkyo_avr.py is part of knxadapter3.py
  Copyright (C) 2023 Andreas Frisch <knxadapter@fraxinas.dev>

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
from eiscp import core as onkyo

def plugin_def():
    return OnkyoAVR

class OnkyoAVR(BasePlugin):
    def __init__(self, daemon, cfg):
        super(OnkyoAVR, self).__init__(daemon, cfg)
        self.avr_reader = None
        self.avr_writer = None
        daemon.knx_read_cbs.append(self.process_knx)
        log.debug("{} obj_list: {!r}".format(self.device_name, self.obj_list))

    async def avr_client(self):
        self.avr_reader, self.avr_writer = await asyncio.open_connection(
            self.cfg["host"], self.cfg["port"])

    async def send_avr(self, iscp_command):
        rawdata = onkyo.command_to_packet(iscp_command)
        log.debug(f"{self.device_name} sending iscp command {iscp_command} to AVR")
        self.avr_writer.write(rawdata)
        await self.avr_writer.drain()

    def get_value_by_avr(self, avr_object):
        return next(item for item in self.obj_list if item["avr_object"] == avr_object)["value"]

    def get_knx_by_avr(self, avr_object):
        return next(item for item in self.obj_list if item["avr_object"] == avr_object)["knx_group"]

    def set_value_for_avr(self, avr_object, value):
        next(item for item in self.obj_list if item["avr_object"] == avr_object)["value"] = value

    async def process_knx(self, cmd):
        try:
            knx_group, knx_val = cmd.strip().split("=")
            try:
                avr_obj = self.get_obj_by_knxgrp(knx_group)
                if avr_obj["enabled"]:
                    value = int(knx_val)
                    avr_cmd = avr_obj["avr_object"]
                    if "volume" in avr_cmd:
                        value = round((int(knx_val) * 196.0) / 255.0)
                    if value == avr_obj["value"]:
                        #log.debug(f"{self.device_name} {avr_obj} unchanged, ignored!")
                        return True
                    avr_zone = avr_obj["avr_zone"]
                    log.info(f"{self.device_name} {avr_obj} => {avr_cmd}, {value}, zone={avr_zone}")
                    iscp_command = onkyo.command_to_iscp(avr_cmd, [str(value)], zone=avr_zone)
                    await self.send_avr(iscp_command)
                    self.set_value_for_avr(avr_cmd, value)
            except StopIteration:
                pass
            return True
        except Exception as e:
            log.warning(f"{self.device_name} couldn't parse KNX command {cmd} ({str(e)})!")
            return False

    async def handle_avr(self):
        while True:
            group_value_dict = {}

            header_bytes = await self.avr_reader.read(16)
            header = onkyo.eISCPPacket.parse_header(header_bytes)
            body_bytes = await self.avr_reader.read(header.data_size)
            iscp_message = onkyo.ISCPMessage.parse(body_bytes.decode())
            command = onkyo.iscp_to_command(iscp_message)

            try:
                (avr_object, value) = command

                if type(value) == tuple:
                    value = value[-1]

                try:
                    old_val = self.get_value_by_avr(avr_object)
                except StopIteration:
                    old_val = None
                if old_val != value:
                    try:
                        knx_val =  value
                        if "volume" in avr_object:
                            knx_val = round((value * 255.0) / 196.0)
                        knx_grp = self.get_knx_by_avr(avr_object)

                        self.set_value_for_avr(avr_object, value)
                        group_value_dict[knx_grp] = knx_val
                        log.info("{} received {!r} from AVR, set {}={}".format(
                            self.device_name, command, knx_grp, knx_val))
                    except StopIteration:
                        pass
                        #log.debug(f"{self.device_name} command {avr_object} not handled")

                else:
                    pass
                    #log.debug(f"{self.device_name} {avr_object}={value} unchanged, ignored!")

            except:
                log.error(f"{self.device_name} couldn't parse AVR command {command}")

            if group_value_dict:
                await self.d.set_group_value_dict(group_value_dict)

    def _run(self):
        self.client = self.d.loop.run_until_complete(self.avr_client())
        return [self.handle_avr()]
