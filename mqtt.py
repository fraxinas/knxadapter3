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
from asyncio_mqtt import Client, MqttCodeError, MqttError
from json import loads

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
        self.status_pending_for_groups = []

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
            payload = message.payload.decode()
            try:
                jsonobj = loads(payload)
            except ValueError:
                jsonobj = None
                value = str(payload)
            objects = self._get_objects_by_topic(message.topic)
            for o in objects:
                knx_group = o["knx_group"]
                if jsonobj and "valmap" in o:
                    for key, valdict in o["valmap"].items():
                        if key in jsonobj:
                            prop = jsonobj[key]
                            if type(valdict) == dict and prop in valdict:
                                value = valdict[prop]
                            else:
                                value = str(prop)
                        else:
                            value = None
                            continue
                prev_val = o["value"]
                if value == None:
                    pass
                elif prev_val != value:
                    o["value"] = value
                    group_value_dict[knx_group] = value
                    log.debug(f"{self.device_name} mqtt topic={message.topic} payload={payload} knx_group={knx_group} updated value {prev_val}=>{value}")
                    if group_value_dict:
                        await self.d.set_group_value_dict(group_value_dict)
                else:
                    log.debug(f"{self.device_name} mqtt topic={message.topic} payload={payload} knx_group={knx_group} value={value} unchanged, ignored")
                if knx_group in self.status_pending_for_groups:
                    self.status_pending_for_groups.remove(knx_group)

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
        try:
            knx_group, knx_val = cmd.strip().split("=")
            try:
                o = self.get_obj_by_knxgrp(knx_group)
                if o["enabled"]:
                    debug_msg = f"{self.device_name} process_knx({knx_group}={knx_val})"
                    await self._write_mqtt(knx_group, knx_val, debug_msg)
            except StopIteration:
                pass
            return True
        except Exception as e:
            log.warning(f"{self.device_name} couldn't parse KNX command {cmd} ({str(e)})!")
            return False

    async def _write_mqtt(self, knx_group, knx_val, debug_msg):
        if not self._mqtt_client:
            return
        objects = []
        request_status = False
        for item in self.obj_list:
            if item["knx_group"] == knx_group:
                objects.append(item)
                request_status = "request_status" in item
        for o in objects:
            if "publish_topic" in o:
                topic = o["publish_topic"]
                prev_val = o["value"]
                if "valmap" in o:
                    payload = o["valmap"][knx_val]
                else:
                    payload = knx_val
                log.info(f"{debug_msg} topic {topic} updating {prev_val}=>{knx_val} ({payload})")
                try:
                    await self._mqtt_client.publish(topic, payload, qos=1, retain=True)
                    o["value"] = knx_val
                except MqttCodeError as error:
                    log.error(f"{debug_msg} MqttCodeError {error} on topic {topic}")
        if objects and request_status and "status_object" in self.cfg and self._mqtt_client and not knx_group in self.status_pending_for_groups:
            so = self.cfg["status_object"]
            delay = so.get("delay", 10.0)
            topic = so["topic"]
            payload = so["payload"]
            await asyncio.sleep(delay)
            try:
                await self._mqtt_client.publish(topic, payload, qos=1, retain=True)
                log.debug(f"{debug_msg} requested status topic {topic} payload=>{payload}")
                self.status_pending_for_groups.append(knx_group)
            except MqttCodeError as error:
                log.error(f"{debug_msg} MqttCodeError {error} on topic {topic}")

    def _get_objects_by_topic(self, topic):
        objects = []
        for item in self.obj_list:
            if item["topic"] == topic:
                objects.append(item)
        return objects

    def _run(self):
        loop_task = self.d.loop.create_task(self.mqtt_loop())
        return [loop_task]
