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
                     "LED": (gpiozero.LED, GPIO_DIRECTION_OUTPUT),
                     "DIG_OUTPUT": (gpiozero.DigitalOutputDevice, GPIO_DIRECTION_OUTPUT)}
    GPIO_ACTION_MAP = {"PRESSED": "when_pressed", "RELEASED": "when_released", "HELD": "when_held",
                       "ON": "on", "OFF": "off", "TOGGLE": "toggle"}

    def __init__(self, daemon, cfg):
        super(gpio, self).__init__(daemon, cfg)
        daemon.knx_read_cbs.append(self.process_knx)
        daemon.value_direct_cbs.append(self.process_direct)
        for o in cfg["objects"]:
            gpio_type = o["gpio_type"]
            gpio_pin = o["gpio_pin"]
            if o["enabled"] and gpio_type in self.GPIO_TYPE_MAP:
                gpio_obj = self.GPIO_TYPE_MAP[gpio_type][0](gpio_pin)
                o["gpio_object"] = gpio_obj
                o["gpio_direction"] = self.GPIO_TYPE_MAP[gpio_type][1]
                for key, val in o["actions"].items():
                    if o["gpio_direction"] == self.GPIO_DIRECTION_INPUT:
                        action = key
                        value = val
                    elif o["gpio_direction"] == self.GPIO_DIRECTION_OUTPUT:
                        action = val
                        value = key
                    if action in self.GPIO_ACTION_MAP:
                        actioncbname = self.GPIO_ACTION_MAP[action]
                        if hasattr(gpio_obj, actioncbname):
                            actioncb = (lambda value: lambda evt: self.gpio_action(evt, o["knx_group"], value))(value)
                            if o["gpio_direction"] == self.GPIO_DIRECTION_INPUT:
                                setattr(gpio_obj, actioncbname, actioncb)
                                log.debug(f"{self.device_name} init. on callback='{actioncbname}' set value='{value}' for {o!r}")
                            else:
                                o["set_cb"] = getattr(gpio_obj, actioncbname)
                                log.debug(f"{self.device_name} init. on value change to '{value}', call='{actioncbname}' for {o!r}")
                        else:
                            log.warning(f"{self.device_name} init illegal action '{actioncbname}' for {gpio_obj!r}")
        log.debug("{} obj_list: {!r}".format(self.device_name, self.obj_list))

    def gpio_action(self, evt, group, value):
        asyncio.run_coroutine_threadsafe(self.handle_gpio(group, value), self.d.loop).result()

    async def handle_gpio(self, group, value):
        await self.d.set_group_value_dict({group: value})

    def _get_output_obj_by_knxgrp_and_value(self, knx_group, value):
        for item in self.obj_list:
            if item["knx_group"] == knx_group and item["gpio_direction"] == self.GPIO_DIRECTION_OUTPUT:
                if value in item["actions"]:
                    return item
        return None

    async def process_direct(self, group, value):
        log.debug(f"{self.device_name} process_direct(group={group}, value={value})")
        try:
            o = self._get_output_obj_by_knxgrp_and_value(group, value)
            if o:
                await self.set_gpio(o, value)
            else:
                log.debug(f"{self.device_name} no gpio output found.")
        except StopIteration:
            return

    async def process_knx(self, cmd):
        try:
            knx_grp, raw = cmd.split("=")
            value = raw.strip()
            log.debug(f"{self.device_name} process_knx(group={knx_grp}, value={value})")
            o = self._get_output_obj_by_knxgrp_and_value(knx_grp, value)
            if o:
                await self.set_gpio(o, value)
            else:
                log.debug(f"{self.device_name} no gpio output found.")
            return True
        except:
            return False

    async def set_gpio(self, o, value):
        log.debug(f"{self.device_name} set_gpio({o!r}, {value})")
        try:
            gpio_obj = o["gpio_object"]
            prev_value = gpio_obj.value
            set_cb = o["set_cb"]
            log.info(f"{self.device_name} set_gpio prev_active={prev_value}->{value}. calling {set_cb!r}...")
            set_cb()
            if "actuate_seconds" in o:
                delay = o["actuate_seconds"]
                log.debug(f"{self.device_name} waiting {delay} s")
                await asyncio.sleep(delay)
                gpio_obj.value = prev_value
                log.debug(f"{self.device_name} restored previous state")
        except (TypeError, AttributeError):
            log.warning(f"{self.device_name} set_gpio illegal action '{value}' for {gpio_obj!r}")

    def _run(self):
        return []
