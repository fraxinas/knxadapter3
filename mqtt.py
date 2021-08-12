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
        daemon.value_direct_cbs.append(self.process_direct)
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
            username = self.cfg["user"] or None
            password = self.cfg["pass"] or None
            self._mqtt_client = Client(self.cfg["host"],port=self.cfg["port"],username=username,password=password)
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
            knx_groups = self._get_knxgroups_by_topic(message.topic)
            payload = message.payload.decode()
            o = self._get_obj_by_topic(message.topic)
            value = str(payload)
            if "valmap" in o:
                for key, valdict in o[valmap].items():
                    if key in payload:
                        prop = payload[key]
                        if type(valdict) == dict and prop in valdict:
                            value = prop[valdict]
                        else:
                            value = str(prop)

            if knx_group:
                group_value_dict[knx_group] = value
            log.debug("{} mqtt topic={} payload={} value={} (setting knx_group {})".format (self.device_name, message.topic, payload, value, knx_group))
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

    async def process_direct(self, knx_group, knx_val):
        debug_msg = f"{self.device_name} process_direct({knx_group}={knx_val})"
        await self._write_mqtt(knx_group, knx_val, debug_msg)

    async def process_knx(self, cmd):
        knx_group, knx_val = cmd.split("=")
        debug_msg = f"{self.device_name} process_knx({knx_group}={knx_val})"
        await self._write_mqtt(knx_group, knx_val, debug_msg)

    async def _write_mqtt(self, knx_group, knx_val, debug_msg):
        objects = []
        for item in self.obj_list:
            if item["knx_group"] == knx_group:
                objects.append(item)
        for o in objects:
            if "publish_topic" in o:
                topic = o["publish_topic"]
                prev_val = o["value"]
                if "valmap" in o:
                    payload = o["valmap"][knx_val]
                else:
                    payload = knx_val
                log.debug(f"{debug_msg} topic {topic} updating from value {prev_val}")
                task = asyncio.create_task(self._publish_to_topic(o, topic, knx_val, payload))
                self._mqtt_tasks.add(task)
        await asyncio.gather(*self._mqtt_tasks)

    async def _publish_to_topic(self, topic, knx_val, payload):
        if self._mqtt_client:
            await self._mqtt_client.publish(topic, payload=payload, qos=1, retain=True)
            log.info(f"{self.device_name} topic {topic} updated! payload = {payload}")
            o["value"] = knx_val
        else:
            log.error(f"Couldn't publish {topic}={payload} because mqtt is disconnected")

    def _run(self):
        loop_task = self.d.loop.create_task(self.mqtt_loop())
        return [loop_task]
