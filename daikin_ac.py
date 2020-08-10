'''
  daikin_ac.py is part of knxadapter3.py
  Copyright (C) 2020 Andreas Frisch <fraxinas@schaffenburg.org>

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
import logging
from daikinapi import Daikin
from helper import BasePlugin, knxalog as log

class DaikinCtrl(Daikin):
    def __init__(self, host):       
        super(DaikinCtrl, self).__init__(host)

        reqlog = logging.getLogger('urllib3')
        reqlog.setLevel(logging.WARNING)

        self._cached_ctrl_fields = {}
        self._cached_sens_fields = {}

    def receive_info(self):
        self._cached_ctrl_fields = self._get("/aircon/get_control_info")
        log.debug("Daikin AC Control Fields {!r}".format(self._cached_ctrl_fields))
        self._cached_sens_fields = self._get("/aircon/get_sensor_info")
        log.debug("Daikin AC Sensor Fields {!r}".format(self._cached_sens_fields))

    def _get_control(self, all_fields=False):
        """ Replacement for daikinapi function to operate on cached control info """
        return self._cached_ctrl_fields

    def _get_sensor(self):
        """ Replacement for daikinapi function to operate on cached sensor info """
        return self._cached_sens_fields

class DaikinAC(BasePlugin):
    def __init__(self, daemon, cfg):
        super(DaikinAC, self).__init__(daemon, cfg)
        daemon.knx_read_cbs.append(self.process_knx)
        for obj in cfg["objects"]:
            if obj["enabled"]:
                obj.update({"value": None})
        log.debug("Daikin AC obj_list: {!r}".format(self.obj_list))

    async def handle_ac(self):
        log_msg = []
        while True:
            self._client.receive_info()
            sequence = ""

            for o in self.obj_list:
                ac_obj = o["ac_object"]

                if hasattr(self._client, ac_obj):
                    value = getattr(self._client, ac_obj)

                    if value == "A":
                        value = 0
                    elif value == "B":
                        value = 1

                if value == o["value"]:
                    log_msg.append("{!r}: {!r}".format(ac_obj, value))
                    continue

                sequence += '<object id="%s" value="%s"/>' % (o["knx_group"], str(value))
                o["value"] = value

            if sequence:
                await self.d.send_knx(sequence)
            
            if log_msg:
                log.debug("skipped objects: "+', '.join(log_msg))
                log_msg = []

            await asyncio.sleep(10)

    def _get_devobj_by_knxgrp(self, knx_group):
        return next(item for item in self.obj_list if item["knx_group"] == knx_group)["ac_object"]

    def _get_value_by_acobj(self, ac_object):
        return next(item for item in self.obj_list if item["ac_object"] == ac_object)["value"]

    async def process_knx(self, cmd):
        msg = None
        try:
            knx_grp, value = cmd.split("=")
            log.debug("knx_grp={!r} value={!r}".format(knx_grp, value))
            ac_obj = self._get_devobj_by_knxgrp(knx_grp)

            if not ac_obj or ac_obj not in [x["ac_object"] for x in self.obj_list]:
                log.warn("ac_obj {!r} not found".format(ac_obj))
                return

            if "ac_obj" == "fan_rate":
                if value == "0":
                    value = A
                if value == "1":
                    value = B
            elif value in ["off", "false", "disable", "stop", "inactive"]:
                value = 0
            elif value in ["on", "true", "enable", "start", "active"]:
                value = 1

            if str(value) == str(self._get_value_by_acobj(ac_obj)):
                log.debug("ac_obj {!r} value {!r} unchanged!".format(ac_obj, value))
                return

            log.debug("ac_obj={!r} value {!r}=>{!r}".format(ac_obj, self._get_value_by_acobj(ac_obj), value))

            setattr(self._client, ac_obj, value)

        except:
            log.error("Couldn't parse linknx command: {!r}".format(cmd))

    def _run(self):
        self._client = DaikinCtrl(self.cfg["host"])
        handle_task = self.d.loop.create_task(self.handle_ac())
        return [handle_task]