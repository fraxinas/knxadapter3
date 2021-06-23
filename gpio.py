'''
  gpio.py is part of knxadapter3.py
  Copyright (C) 2021 Andreas Frisch <fraxinas@schaffenburg.org>

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
import gpiozero


def plugin_def():
    return gpio

class gpio(BasePlugin):
    (GPIO_DIRECTION_INPUT, GPIO_DIRECTION_OUTPUT) = range(2)
    GPIO_TYPE_MAP = {"BUTTON": (gpiozero.Button, GPIO_DIRECTION_INPUT),
                     "LED": (gpiozero.LED, GPIO_DIRECTION_OUTPUT)}
    GPIO_ACTION_MAP = {"PRESSED": "when_pressed", "RELEASED": "when_released", "HELD": "when_held"}

    def __init__(self, daemon, cfg):
        super(gpio, self).__init__(daemon, cfg)
        daemon.knx_read_cbs.append(self.process_knx)
        daemon.value_direct_cbs.append(self.process_direct)
        log.debug("{} obj_list: {!r}".format(self.device_name, self.obj_list))

        for o in cfg["objects"]:
            gpio_type = o["gpio_type"]
            gpio_pin = o["gpio_pin"]
            if o["enabled"] and gpio_type in self.GPIO_TYPE_MAP:
                gpio_obj = self.GPIO_TYPE_MAP[gpio_type][0](gpio_pin)
                o["gpio_object"] = gpio_obj
                o["gpio_direction"] = self.GPIO_TYPE_MAP[gpio_type][1]
                for action, value in o["actions"].items():
                    if action in self.GPIO_ACTION_MAP:
                        actioncbname = self.GPIO_ACTION_MAP[action]
                        log.debug(f"{self.device_name} init actioncbname='{actioncbname}' for {gpio_obj!r}")
                        if hasattr(gpio_obj, actioncbname):
                            actioncb = lambda evt: self.gpio_action(o, action)
                            setattr(gpio_obj, actioncbname, actioncb)
                            log.debug(f"{self.device_name} init actioncb='{actioncb!r}' for {gpio_obj!r}")
                        else:
                            log.warning(f"{self.device_name} init illegal action '{actioncbname}' for {gpio_obj!r}")

    def gpio_action(self, obj, action):
        asyncio.run_coroutine_threadsafe(self.handle_gpio(obj, action), self.d.loop).result()

    async def handle_gpio(self, obj, action):
        value = obj["actions"][action]
        log.debug(f"{self.device_name} handle_gpio({obj!r}, action={action}) value={value}")
        await self.d.set_group_value_dict({obj["knx_group"]: value})

    async def process_direct(self, group, value):
        try:
            o = self.get_obj_by_knxgrp(group)
            await self.set_gpio(o, value)
        except StopIteration:
            return

    async def process_knx(self, cmd):
        try:
            knx_grp, raw = cmd.split("=")
            log.debug(f"{self.device_name} knx group {knx_grp} raw={raw}")
            try:
                o = self.get_obj_by_knxgrp(knx_grp)
                await self.set_gpio(o, raw)
            except StopIteration:
                return
        except:
            log.error("Couldn't parse linknx command: {!r}".format(cmd))

    async def set_gpio(self, o, value):
        if o["gpio_direction"] != self.GPIO_DIRECTION_OUTPUT:
            return
        try:
            gpio_obj = o["gpio_object"]
            actioncall = getattr(gpio_obj, value)
            actioncall()
        except (TypeError, AttributeError):
            log.warning(f"{self.device_name} set_gpio illegal action '{value}' for {gpio_obj!r}")

    def _run(self):
        return []
