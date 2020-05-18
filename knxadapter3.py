#! /usr/bin/python3
# -*- coding: utf-8 -*-

'''
  knxadapter3.py
  Copyright (C) 2018,2020 Andreas Frisch <fraxinas@schaffenburg.org>

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

import sys
import json
import asyncio
import logging
import re
from aiohttp import web

logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s: %(message)s',
    stream=sys.stderr,
)

log = logging.getLogger(__name__)
def log_async_exception(fun):
    @wraps(fun)
    async def wrapper(*args, **kwargs):
        try:
            return await fun(*args, **kwargs)
        except:
            log.exception("Exception in %r:", fun.__qualname__)
            raise
    return wrapper

class KnxAdapter():
    def __init__(self, argv):
        if len(sys.argv) > 1 and sys.argv[1]:
            cfg_file = sys.argv[1]
        else:
            cfg_file = sys.path[0] + '/config.json'
        try:
            with open(cfg_file) as json_data_file:
                self.cfg = json.load(json_data_file)

        except FileNotFoundError:
            message = "Couldn't open the config file " + cfg_file
            log.error(message, sys.exc_info()[0])
            sys.exit(0)

        v = self.cfg["sys"]["verbosity"]
        levels = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}
        level = v in levels and levels[v] or logging.CRITICAL
        log.setLevel(level)

        self.knx_client_reader = None
        self.knx_client_writer = None

        self.loop = asyncio.get_event_loop()
        self.knx_read_cbs = []

    async def linknx_client(self, loop, knxcfg):
        self.knx_client_reader, self.knx_client_writer = await asyncio.open_connection(
            knxcfg["host"], knxcfg["port"], loop=loop)

    async def knx_server_handler(self, reader, writer):
        data = await reader.readline()
        cmd = data.decode()

        addr = writer.get_extra_info('peername')
        log.debug("Received %r from %r" % (cmd, addr))

        for callback in self.knx_read_cbs:
            await callback(cmd)

        writer.close()

    async def send_knx(self, sequence):
        xml = '<write>' + sequence + '</write>\n\x04'
        log.debug("sending to knx:{!r}".format(xml))
        self.knx_client_writer.write(xml.encode(encoding='utf_8'))
        self.knx_client_writer.drain()
        data = await asyncio.wait_for(self.knx_client_reader.readline(), timeout=30.0)
        log.debug("received {!r}".format(data.decode()))

    def start(self):
        log.info("Started KNX Bus Adapter Deamon.")

        knx_client = self.loop.run_until_complete(self.linknx_client(self.loop, self.cfg["linknx"]))

        knx_server_coro = asyncio.start_server(self.knx_server_handler, self.cfg["sys"]["listenHost"], self.cfg["linknx"]["listenPort"], loop=self.loop)
        knx_server = self.loop.run_until_complete(knx_server_coro)

        services = []
        services.append(WeatherStation(self))
        services.append(PioneerAVR(self))
        services.append(ApcUps(self))
        services.append(SmartMeter(self))

        tasks = []
        for service in services:
            task = service.run()
            if task:
                tasks += task

        futs = asyncio.gather(*tasks)
        log.info("tasks={!r}\ntasks={!r}".format(tasks, futs))
        self.loop.run_until_complete(futs)

        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            knx_server.close()
            self.loop.run_until_complete(knx_server.wait_closed())
            for service in services:
                service.quit()
            self.loop.close()

class WeatherStation():
    Unit_converter = {
        "mph_to_kmh": lambda v: (v*1.60934),
        "F_to_C": lambda t: ((t-32) / 1.8),
        "inch_to_mm": lambda h: (h*25.4),
        "inHg_to_hPa": lambda h: (h*33.8637526)
    }

    def __init__(self, daemon):
        self.previous_values = {}
        self.d = daemon
        self.ws_app = None
        self.ws_handler = None
        self.ws_server = None

    async def process_values(self, query):
        sequence = ""
        for obj in self.d.cfg["weather_station"]["objects"]:
            sensor = obj["sensor"]
            group = obj["knx_group"]
            debug_msg = "%s->%s" % (sensor, group)

            if sensor in query and obj["enabled"]:
                try:
                    value = float(query[sensor])
                    if value == -9999:
                        log.debug("bogus value for {}, ignored!".format(debug_msg))
                        continue
                    debug_msg += " numeric value: {0:g}".format(value)
                    conversion = obj["conversion"]
                    if conversion and conversion in self.Unit_converter:
                        value = round(self.Unit_converter[conversion](value), 2)
                        debug_msg += "^={0:g}".format(value)

                    if group in self.previous_values:
                        hysteresis = obj["hysteresis"]
                        prev_val = self.previous_values[group]
                        if obj["hysteresis"]:
                            if abs(value - prev_val) <= hysteresis:
                                log.debug("{0}-{1:g}<{2:g} hysteresis, ignored!".
                                      format(debug_msg, prev_val, hysteresis))
                                continue
                        elif prev_val == value:
                            log.debug("{!r} unchanged, ignored!".format(debug_msg))
                            continue
                    sequence += '<object id="%s" value="%.2f"/>' % (group, value)

                except ValueError:
                    value = query[sensor]
                    debug_msg += " non-numeric value:", value
                    if group in self.previous_values and value == self.previous_values[group]:
                        log.debug("{!r} unchanged, ignored!".format(debug_msg))
                        continue
                    sequence += '<object id="%s" value="%s"/>' % (group, value)
                self.previous_values[group] = value
                log.debug(debug_msg)

        if sequence:
            await self.d.send_knx(sequence)

    async def handle(self, request):
        log.debug("handle: {!r}".format(request.rel_url.query))
        await self.process_values(request.rel_url.query)
        return web.Response(text="success\n")

    def run(self):
        if self.d.cfg["weather_station"]["enabled"]:
            self.ws_app = web.Application(debug=True)
            self.ws_app.router.add_get('/weatherstation/{name}', self.handle)
            self.ws_handler = self.ws_app.make_handler()
            log.info("running weather station receiver...")
            ws_coro = self.d.loop.create_server(self.ws_handler, self.d.cfg["sys"]["listenHost"], self.d.cfg["weather_station"]["listenPort"])
            self.ws_server = self.d.loop.run_until_complete(ws_coro)
            return None

    def quit(self):
        if self.ws_server:
            log.info("quit weather station receiver...")
            self.ws_server.close()
            self.d.loop.run_until_complete(self.ws_app.shutdown())
            self.d.loop.run_until_complete(self.ws_handler.shutdown(2.0))
            self.d.loop.run_until_complete(self.ws_app.cleanup())

class PioneerAVR():
    def __init__(self, daemon):
        self.current_values = {}
        self.accu_word = None
        self.d = daemon
        self.avr_client = None
        self.avr_reader = None
        self.avr_writer = None
        daemon.knx_read_cbs.append(self.process_knx)
        self.objd = {}
        for obj in self.d.cfg["avr"]["objects"]:
            avr_obj = obj["avr_object"]
            self.objd[avr_obj] = obj["knx_group"]
            self.current_values[avr_obj] = None

    async def avr_client(self, loop, avrcfg):
        self.avr_reader, self.avr_writer = await asyncio.open_connection(
            avrcfg["host"], avrcfg["port"], loop=loop)

    async def send_avr(self, data):
        log.debug("sending to avr: '%s'" % data)
        self.avr_writer.write((data+'\r').encode(encoding='ascii'))
        self.avr_writer.drain()

    async def process_knx(self, cmd):
        msg = None
        log.debug("avr processes knx command '%r'" % cmd)
        if 1:
        #try:
            if cmd[0] == 'P':
                if cmd[1:3] == "on" and self.current_values["power"] != "on":
                    msg = "PO"
                elif cmd[1:4] == "off" and self.current_values["power"] != "off":
                    msg = "PF"
            elif cmd[0] == 'V':
                new_vol = int(cmd[1:])
                if new_vol != self.current_values["volume"]:
                    avr_vol = round(new_vol * (185.0 / 255.0))
                    msg = "%03dVL" % avr_vol
                    self.current_values["volume"] = new_vol
            elif cmd[0] == 'F':
                new_fn = int(cmd[1:3])
                if new_fn in range (0,32) and new_fn != self.current_values["fn"]:
                    msg = "%02dFN" % new_fn
                    self.current_values["fn"] = new_fn
            if msg:
                await self.send_avr(msg)
        #except:
            #log.error("Couldn't parse linknx command: {!r}".format(cmd))

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
                self.current_values["display_text"] = self.accu_word
                sequence = '<object id="%s" value="%s"/>' % (self.objd["display_text"], self.current_values["display_text"])
                log.debug("display_text complete! '%s'" % self.current_values["display_text"])
              else:
                new_word = bytes.fromhex(line[4:-2]).decode('iso8859_15')
                if self.accu_word == None:
                    self.accu_word = new_word
                    log.debug("1START new_word={!r} accu_word={!r}".format(new_word, self.accu_word))
                elif self.accu_word[-13:] != new_word[:-1]:
                    #if self.current_values["display_text"] and self.current_values["display_text"].startswith(new_word):
                        #log.debug("STARTOVER new_word={!r} accu_word={!r}".format(new_word, self.accu_word))
                    if not self.current_values["display_text"] or new_word not in self.current_values["display_text"]:
                        self.current_values["display_text"] = None
                        self.accu_word = new_word
                        sequence = '<object id="%s" value="%s"/>' % (self.objd["display_text"], self.accu_word)
                        log.debug("CHANGE new_word={!r} accu_word={!r} {}".format(new_word, self.accu_word, sequence))
                    else:
                        log.debug("STARTOVER new_word={!r} accu_word={!r}".format(new_word, self.accu_word))
                else:
                  self.accu_word += new_word[-1:]
                  log.debug("+++++ new_word={!r} accu_word={!r}".format(new_word, self.accu_word))
                if not self.current_values["display_text"] and self.accu_word[-1] != ' ':
                  sequence = '<object id="%s" value="%s"/>' % (self.objd["display_text"], self.accu_word.rstrip())
                  log.debug("COMMIT new_word={!r} accu_word={!r} {}".format(new_word, self.accu_word, sequence))

            elif line.startswith('VOL'):
              avr_volume = int(line[3:])
              new_volume = round(avr_volume * (255.0 / 185.0))
              if new_volume != self.current_values["volume"]:
                self.current_values["volume"] = new_volume
                sequence = '<object id="%s" value="%d"/>' % (self.objd["volume"], self.current_values["volume"])

            elif line.startswith('PWR'):
              if line[3] == '0':
                self.current_values["power"] = "on"
              else:
                self.current_values["power"] = "off"
              sequence = '<object id="%s" value="%s"/>' % (self.objd["power"], self.current_values["power"])
              self.current_values["display_text"] = None
              sequence += '<object id="%s" value="%s"/>' % (self.objd["display_text"], self.current_values["display_text"])

            elif line.startswith('FN'):
              new_fn = int(line[2:4])
              if new_fn != self.current_values["fn"]:
                self.current_values["fn"] = new_fn
                sequence = '<object id="%s" value="%d"/>' % (self.objd["fn"], self.current_values["fn"])
                self.current_values["display_text"] = None
                sequence += '<object id="%s" value="%s"/>' % (self.objd["display_text"], self.current_values["display_text"])

            if sequence:
              await self.d.send_knx(sequence)

    def run(self):
        if self.d.cfg["avr"]["enabled"]:
            log.info("running Pioneer AVR Client...")
            self.avr_client = self.d.loop.run_until_complete(self.avr_client(self.d.loop, self.d.cfg["avr"]))
            return [self.handle_avr()]

    def quit(self):
        if self.avr_client:
            log.info("quit Pioneer AVR Client...")
            self.avr_client.close()

class ApcUps():
    def __init__(self, daemon):
        self.current_values = {}
        self.d = daemon
        self.ups_client = None
        self.ups_reader = None
        self.ups_writer = None
        self.obj_list = []
        self.expression = ".*?"
        self.hysd = {}
        self.previous_values = {}
        for obj in self.d.cfg["ups"]["objects"]:
            if obj["enabled"]:
                ups_expr = obj["ups_expr"]
                self.expression += ups_expr + '.*?'
                group = obj["knx_group"]
                self.obj_list.append(group)
                self.current_values[group] = None
                if "hysteresis" in obj:
                    self.hysd[group] = obj["hysteresis"]

    async def ups_client(self, loop, upscfg):
        self.ups_reader, self.ups_writer = await asyncio.open_connection(
            upscfg["host"], upscfg["port"], loop=loop)

    async def poll_ups(self):
        while True:
            hello = (chr(0)+chr(6)+"status").encode('ascii')
            print ("polling ups", hello)
            self.ups_writer.write(hello)
            await self.ups_writer.drain()
            await asyncio.sleep(10)

    async def handle_ups(self):
        log.debug('handle_ups...')
        while True:
            data = await self.ups_reader.readuntil(b'\x00\x00')
            log.debug('ups received {!r}'.format(data))

            if not data:
                break
            
            data = data.decode('ascii')

            log.debug('received apcups data {!r}'.format(data))

            m = re.match(self.expression, data, re.DOTALL)
            log.info("match: "+str(m))

            if m:
                print(m.groups())
                sequence = ""
                
                for idx, group in enumerate(self.obj_list):
                    val = m.groups(0)[idx]
                    debug_msg = "idx: {0} group: {1} val: {2}".format(idx, group, val)
                    try:
                        value = float(val)
                        debug_msg += " numeric value: {0:g}".format(value)
                        if group in self.previous_values:
                            prev_val = self.previous_values[group]
                            if self.hysd[group]:
                                if abs(value - prev_val) <= self.hysd[group]:
                                    log.debug("{0} {1}-{2:g}<{3:g} hysteresis, ignored!".
                                        format(group, value, prev_val, self.hysd[group]))
                                    continue
                                else:
                                    debug_msg += " (previous value: {0:g})".format(prev_val)
                            elif prev_val == value:
                                log.debug("{!r} unchanged, ignored!".format(debug_msg))
                                continue
                        sequence += '<object id="%s" value="%.2f"/>' % (group, value)
                    
                    except ValueError:
                        if val == "ONLINE":
                            value = "true"
                        elif val == "ONBATT":
                            value = "false"
                        debug_msg += " non-numeric value: {0}->{1}".format(val, value)
                        if group in self.previous_values and value == self.previous_values[group]:
                            log.debug("{!r} unchanged, ignored!".format(debug_msg))
                            continue
                        sequence += '<object id="%s" value="%s"/>' % (group, value)
                    self.previous_values[group] = value
                    log.debug(debug_msg)

                if sequence:
                    await self.d.send_knx(sequence)

    def run(self):
        if self.d.cfg["ups"]["enabled"]:
            log.info("running APC UPS Client...")
            self.ups_client = self.d.loop.run_until_complete(self.ups_client(self.d.loop, self.d.cfg["ups"]))
            poll_task = self.d.loop.create_task(self.poll_ups())
            return [self.handle_ups(), poll_task]

    def quit(self):
        if self.ups_client:
            log.info("quit APC UPS Client...")
            self.ups_client.close()

class SmartMeter():
    def _read_i32(self,register):
        r1=self.client.read_holding_registers(register,2,unit=71)
        U32register = self.modbus_bin_pay_dec.fromRegisters(r1.registers, byteorder=self.endianness, wordorder=self.endianness)
        result_U32register = U32register.decode_32bit_int()
        return result_U32register

    def _read_u64(self,register):
        r1=self.client.read_holding_registers(register,4,unit=71)
        U64register = self.modbus_bin_pay_dec.fromRegisters(r1.registers, byteorder=self.endianness, wordorder=self.endianness)
        result_U64register = U64register.decode_64bit_uint()
        return result_U64register

    def _read_u32(self,register):
        r1=self.client.read_holding_registers(register,2,unit=71)
        U32register = self.modbus_bin_pay_dec.fromRegisters(r1.registers, byteorder=self.endianness, wordorder=self.endianness)
        result_U32register = U32register.decode_32bit_uint()
        return result_U32register

    def _read_modbus(self, data_type, register):
        methods = {"I32": self._read_i32, "U32": self._read_u32, "U64": self._read_u64}
        ret = None
        try:
            func = methods[data_type]
            ret = func(register)
        except KeyError:
            log.warning("Smart Meter Data Type {} not found for register {}".format(data_type, register))
        except:
            log.warning("Couldn't read register {} from Smart Meter".format(register))
        return ret

    def __init__(self, daemon):
        modbuslog = logging.getLogger('pymodbus')
        modbuslog.setLevel(logging.ERROR)

        self.current_values = {}
        self.d = daemon
        self.client = None
        self.obj_list = []
        cfg = self.d.cfg["smart_meter"]
        self.default_magnitude = "default_magnitude" in cfg and cfg["default_magnitude"] or 1.0
        self.default_hysteresis = "default_hysteresis" in cfg and cfg["default_hysteresis"] or 0

        for o in self.d.cfg["smart_meter"]["objects"]:
            if o["enabled"]:
                o.update({"value": 0, "previous_value": 0})
                self.obj_list.append(o)

    async def handle_sm(self):
        log.debug('handle_sm...')
        from pymodbus.constants import Endian
        from pymodbus.payload import BinaryPayloadDecoder
        self.endianness = Endian.Big
        self.modbus_bin_pay_dec = BinaryPayloadDecoder
        while True:
            sequence = ""

            for o in self.obj_list:
                register = o["register"]
                raw_val = self._read_modbus(o["data_type"], o["register"])
                if raw_val is None:
                    continue
                prev_val = o["value"]

                mag = ("magnitude" in o and o["magnitude"] or self.default_magnitude)

                if o["data_type"] == "U64":
                    value = int(round(raw_val * mag, 0))
                else:
                    value = round(raw_val * mag, 3)

                debug_msg = "Smart Meter read {} raw={} => value={}".format(o["knx_group"], raw_val, value)

                hysteresis = "hysteresis" in o and o["hysteresis"] or self.default_hysteresis
                if type(hysteresis) == str and "%" in hysteresis and abs(value - prev_val) <= float(hysteresis.strip('%'))*value*0.01 or type(hysteresis) == float and abs(value - prev_val) <= hysteresis:
                    log.debug("{0} {1}-{2:g}<{3} hysteresis, ignored!".format(debug_msg, value, prev_val, hysteresis))
                    continue
                elif prev_val == value:
                    log.debug("{!r} unchanged, ignored!".format(debug_msg))
                    continue
                else:
                    log.debug(debug_msg)

                str_value = "%.2f" % value if o["data_type"]!="U64" else str(value)
                sequence += '<object id="%s" value="%s"/>' % (o["knx_group"], str_value)

                o["previous_value"] = prev_val
                o["value"] = value

            if sequence:
                await self.d.send_knx(sequence)

            await asyncio.sleep(1)

    def run(self):
        cfg = self.d.cfg["smart_meter"]
        if cfg["enabled"]:
            import pymodbus
            from pymodbus.client.sync import ModbusTcpClient
            log.info("running Smart Meter Client...")
            self.client = ModbusTcpClient(cfg["host"],port=cfg["port"])
            self.client.connect()
            handle_task = self.d.loop.create_task(self.handle_sm())
            return [handle_task]

    def quit(self):
        if self.client:
            log.info("quit Smart Meter Client...")

if __name__ == "__main__":
    knx_adapter = KnxAdapter(sys.argv[1:])
    knx_adapter.start()

