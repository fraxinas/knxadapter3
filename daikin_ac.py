'''
  daikin_ac.py is part of knxadapter3.py
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
import logging
from helper import BasePlugin, knxalog as log
from daikinapi import Daikin
from requests import ConnectionError

def plugin_def():
    return DaikinAC

class DaikinAC(BasePlugin):
    def __init__(self, daemon, cfg):
        super(DaikinAC, self).__init__(daemon, cfg)
        daemon.knx_read_cbs.append(self.process_knx)
        self.poll_interval = "poll_interval" in cfg and cfg["poll_interval"] or 10
        for obj in cfg["objects"]:
            if obj["enabled"]:
                obj.update({"value": None})
        log.debug("{} obj_list: {!r}".format(self.device_name, self.obj_list))

    async def handle_ac(self):
        log_msg = []
        while True:
            self._client.receive_info()
            group_value_dict = {}

            for o in self.obj_list:
                ac_obj = o["ac_object"]

                try:
                    value = getattr(self._client, ac_obj)

                    if value == "A":
                        value = 0
                    elif value == "B":
                        value = 1
                except KeyError:
                    continue
                except ValueError as e:
                    log.debug("{} {!r} on key {}".format(self.device_name, e, ac_obj))
                    continue

                if value == o["value"]:
                    log_msg.append("{!r}: {!r}".format(ac_obj, value))
                    continue

                group_value_dict[o["knx_group"]] = str(value)
                o["value"] = value

            if group_value_dict:
                await self.d.set_group_value_dict(group_value_dict)

            if log_msg:
                log.debug(self.device_name+" skipped objects: "+', '.join(log_msg))
                log_msg = []

            await asyncio.sleep(self.poll_interval)

    def _get_value_by_acobj(self, ac_object):
        return next(item for item in self.obj_list if item["ac_object"] == ac_object)["value"]

    async def process_knx(self, cmd):
        msg = None
        try:
            knx_grp, raw = cmd.split("=")
            debug_msg = "{} knx group {} raw={}".format(self.device_name, knx_grp, raw)

            try:
                ac_obj = self.get_obj_by_knxgrp(knx_grp)["ac_object"]
            except StopIteration:
                log.debug("{} no AC object for given KNX group, ignored".format(debug_msg))
                return True

            if ac_obj == "fan_rate":
                if raw == "0":
                    value = "A"
                elif raw== "1":
                    value = "B"
            elif raw in ["off", "false", "disable", "stop", "inactive"]:
                value = 0
            elif raw in ["on", "true", "enable", "start", "active"]:
                value = 1
            else:
                value = raw

            if str(value) == str(self._get_value_by_acobj(ac_obj)):
                log.debug("{} ac_obj {} unchanged value {}->{}, ignored!".format(debug_msg, ac_obj, str(self._get_value_by_acobj(ac_obj)), str(value)))
                return True

            log.debug("{} ac_obj {} updated value {}=>{}".format(debug_msg, ac_obj, self._get_value_by_acobj(ac_obj), value))
            setattr(self._client, ac_obj, value)
            return True

        except:
            return False

    def _run(self):
        class DaikinCtrl(Daikin):
            def __init__(self, host):
                super(DaikinCtrl, self).__init__(host)

                reqlog = logging.getLogger('urllib3')
                reqlog.setLevel(logging.WARNING)

                self._cached_ctrl_fields = {}
                self._cached_sens_fields = {}

            def receive_info(self):
                try:
                    self._cached_ctrl_fields = self._get("/aircon/get_control_info")
                    log.debug("Daikin AC Control Fields {!r}".format(self._cached_ctrl_fields))
                    self._cached_sens_fields = self._get("/aircon/get_sensor_info")
                    log.debug("Daikin AC Sensor Fields {!r}".format(self._cached_sens_fields))
                except ConnectionError as e:
                    log.warning("Daikin AC Couldn't perform API read {!r}".format(e))

            def _get_control(self, all_fields=False):
                """ Replacement for daikinapi function to operate on cached control info """
                return self._cached_ctrl_fields

            def _get_sensor(self):
                """ Replacement for daikinapi function to operate on cached sensor info """
                return self._cached_sens_fields

        self._client = DaikinCtrl(self.cfg["host"])
        handle_task = self.d.loop.create_task(self.handle_ac())
        return [handle_task]
