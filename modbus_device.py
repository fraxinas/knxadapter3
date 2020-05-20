'''
  modbus_device.py is part of knxadapter3.py
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
from helper import BasePlugin, knxalog as log

class ModbusDevice(BasePlugin):
    def _read_float(self,register):
        reg = self.client.read_holding_registers(register, 2, unit=71)
        pay = self.modbus_bin_pay_dec.fromRegisters(reg.registers, byteorder=self._BE, wordorder=self.wordorder)
        return round(pay.decode_32bit_float(), 2)

    def _read_i16(self,register):
        reg = self.client.read_holding_registers(register, 1, unit=71)
        pay = self.modbus_bin_pay_dec.fromRegisters(reg.registers, byteorder=self._BE, wordorder=self.wordorder)
        return pay.decode_16bit_int()

    def _read_u16(self,register):
        reg = self.client.read_holding_registers(register, 1, unit=71)
        pay = self.modbus_bin_pay_dec.fromRegisters(reg.registers, byteorder=self._BE, wordorder=self.wordorder)
        return pay.decode_16bit_uint()

    def _read_i32(self,register):
        reg = self.client.read_holding_registers(register, 2, unit=71)
        pay = self.modbus_bin_pay_dec.fromRegisters(reg.registers, byteorder=self._BE, wordorder=self.wordorder)
        return pay.decode_32bit_int()

    def _read_u32(self,register):
        reg = self.client.read_holding_registers(register, 2, unit=71)
        pay = self.modbus_bin_pay_dec.fromRegisters(reg.registers, byteorder=self._BE, wordorder=self.wordorder)
        return pay.decode_32bit_uint()

    def _read_u64(self,register):
        reg = self.client.read_holding_registers(register, 4, unit=71)
        pay = self.modbus_bin_pay_dec.fromRegisters(reg.registers, byteorder=self._BE, wordorder=self.wordorder)
        return pay.decode_64bit_uint()

    def _read_modbus(self, data_type, register):
        methods = {"float": self._read_float, "I16": self._read_i16, "U16": self._read_u16, "I32": self._read_i32, "U32": self._read_u32, "U64": self._read_u64}
        ret = None
        try:
            func = methods[data_type]
            ret = func(register)
        except KeyError:
            log.warning("Modbus Data Type {} not found for register {} on device {}".format(data_type, register, self.device_name))
        except:
            log.warning("Couldn't read register {} from Modbus device {}".format(register, self.device_name))
        return ret

    def __init__(self, daemon, cfg):
        super(ModbusDevice, self).__init__(daemon, cfg)
        modbuslog = logging.getLogger('pymodbus')
        modbuslog.setLevel(logging.ERROR)

        default_magnitude = "default_magnitude" in self.cfg and self.cfg["default_magnitude"] or 1.0
        for obj in self.obj_list:
            if not "magnitude" in obj:
                obj.update({"magnitude": default_magnitude})

    async def handle_sm(self):
        log.debug('handle_sm...')
        from pymodbus.constants import Endian
        from pymodbus.payload import BinaryPayloadDecoder
        self._BE = Endian.Big
        if self.cfg["modbus_wordorder"] == "LE":
            self.wordorder = Endian.Little
        else:
            self.wordorder = Endian.Big
        self.modbus_bin_pay_dec = BinaryPayloadDecoder
        while True:
            sequence = ""

            print("obj_list:", self.obj_list)

            for o in self.obj_list:
                register = o["register"]
                raw_val = self._read_modbus(o["data_type"], o["register"])
                if raw_val is None:
                    continue
                prev_val = o["value"]

                mag = o["magnitude"]
                if o["data_type"] == "U64":
                    value = int(round(raw_val * mag, 0))
                else:
                    value = round(raw_val * mag, 3)

                debug_msg = "{} read {} raw={} => value={}".format(self.device_name, o["knx_group"], raw_val, value)

                hysteresis = o["hysteresis"]
                if type(hysteresis) == str and "%" in hysteresis and abs(value - prev_val) <= float(hysteresis.strip('%'))*value*0.01 or type(hysteresis) == float and abs(value - prev_val) <= hysteresis:
                    log.debug("{0} {1}-{2:g} < {3} hysteresis, ignored!".format(debug_msg, value, prev_val, hysteresis))
                    continue
                elif prev_val == value:
                    log.debug("{!r} unchanged, ignored!".format(debug_msg))
                    continue
                else:
                    log.debug(debug_msg)

                str_value = "%.2f" % value if o["data_type"]!="U64" else str(value)
                sequence += '<object id="%s" value="%s"/>' % (o["knx_group"], str_value)

                o["value"] = value

            if sequence:
                await self.d.send_knx(sequence)

            await asyncio.sleep(1)

    def _run(self):
        import pymodbus
        from pymodbus.client.sync import ModbusTcpClient
        self.client = ModbusTcpClient(self.cfg["host"],port=self.cfg["port"])
        self.client.connect()
        handle_task = self.d.loop.create_task(self.handle_sm())
        return [handle_task]
