'''
  mqtt.py is part of knxadapter3.py
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

import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from helper import BasePlugin, knxalog as log
from asyncio_mqtt import Client, MqttError

def plugin_def():
    return MQTT

class MQTT(BasePlugin):
    def __init__(self, daemon, cfg):
        super(MQTT, self).__init__(daemon, cfg)
        daemon.knx_read_cbs.append(self.process_knx)
        self.poll_interval = "poll_interval" in cfg and cfg["poll_interval"] or 10
        self._mqtt_tasks = None
        self._mqtt_client = None

    async def mqtt_loop(self):
        while True:
          try:
              await self.mqtt_stack()
          except MqttError as error:
              log.warning("MqttError: {error}. Reconnecting in {self.poll_interval} seconds.")
          finally:
              await asyncio.sleep(self.poll_interval)

    async def mqtt_stack(self):
        async with AsyncExitStack() as stack:
            self._mqtt_tasks = set()
            stack.push_async_callback(self.cancel_tasks, self._mqtt_tasks)

            self._mqtt_client = Client(self.cfg["host"],port=self.cfg["port"])
            await stack.enter_async_context(self._mqtt_client)

            topics = []
            for o in self.obj_list:
                topic = o["topic"]
                topics.append(topic)
                manager = self._mqtt_client.filtered_messages(topic)
                messages = await stack.enter_async_context(manager)
                task = asyncio.create_task(self.mqtt_handle(messages, o))
                self._mqtt_tasks.add(task)

            for topic in topics:
                await self._mqtt_client.subscribe(topic)

            await asyncio.gather(*self._mqtt_tasks)

    async def mqtt_handle(self, messages, obj):
        group_value_dict = {}
        async for message in messages:
            knx_group = self._get_knxgrp_by_topic(message.topic)
            value = str(message.payload.decode())
            if knx_group:
                group_value_dict[knx_group] = value
            log.debug("%s: %s (knx_group=%s)" % (message.topic, value, knx_group))
            if group_value_dict:
                await self.d.set_group_value_dict(group_value_dict)
            obj["value"] = value

    async def cancel_tasks(self):
        for task in self._mqtt_tasks:
            if task.done():
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def process_knx(self, cmd):
        try:
            knx_group, value = cmd.split("=")
            debug_msg = "{} knx {} value={}".format(self.device_name, knx_group, value)

            try:
                topic = self._get_topic_by_knxgrp(knx_group)
            except StopIteration:
                log.debug("{} no publish_topic for given KNX group, ignored".format(debug_msg))
                return True

            prev_val = self._get_value_by_knxgrp(knx_group)
            if str(value) == str(prev_val):
                log.debug("{} topic {} unchanged value {}->{}, ignored!".format(debug_msg, topic, str(self._get_value_by_knxgrp(knx_group)), str(value)))
                return True

            log.debug("{} topic {} updated value {}=>{}".format(debug_msg, topic, prev_val, value))

            task = asyncio.create_task(self._publish_to_topic(topic, value))
            self._mqtt_tasks.add(task)

            await asyncio.gather(*self._mqtt_tasks)
            return True

        except:
            return False

    async def _publish_to_topic(self, topic, value):
        if self._mqtt_client:
            await self._mqtt_client.publish(topic, value, qos=1)
            self._set_value_by_publishtopic(topic, value)
        else:
            log.error("Couldn't publish {}={} because mqtt is disconnected".format(topic, value))

    def _get_knxgrp_by_topic(self, topic):
        return next(item for item in self.obj_list if item["topic"] == topic)["knx_group"]

    def _get_topic_by_knxgrp(self, knx_group):
        return next(item for item in self.obj_list if item["knx_group"] == knx_group)["publish_topic"]

    def _get_value_by_knxgrp(self, knx_group):
        return next(item for item in self.obj_list if item["knx_group"] == knx_group)["value"]

    def _set_value_by_publishtopic(self, topic, value):
        next(item for item in self.obj_list if item.get("publish_topic") == topic)["value"] = value

    def _run(self):
        loop_task = self.d.loop.create_task(self.mqtt_loop())
        return [loop_task]
