#!/usr/bin/python2.7 --

import usb.core
import usb.util


class PType(object):
    DATA            = 0x0
    RESET           = 0x1
    READ_BLOCK      = 0x2
    READ_PRESSURE   = 0x3
    FAKE_LAUNCH     = 0x4
    COMPLETE        = 0x5
    ERASE_MEM       = 0x6
    READ_BAT        = 0x7
    READ_SETTINGS   = 0x8
    WRITE_SETTINGS  = 0x9
    FIRE_LINES      = 0xa
    RECORDING_DATA  = 0xb

    def __init__(self, t):
        if t < 0 or t > 0xb:
            raise ValueError("Valid PType values are 0..11")
        self.t = int(t)

    def __int__(self):
        return self.t

    def __eq__(self, t):
        return self.t == int(t)

    def __ne__(self, t):
        return self.t != int(t)

    def value(self):
        return self.t


class Packet(object):
    def __init__(self, data, t=None):
        if t is None:
            if len(data) == 3:
                self.v = (int(data[1]) << 8) + int(data[0])
                self.t = PType(data[2])
            elif len(data) == 2:
                self.v = int(data[0])
                self.t = PType(data[1])
            else:
                raise ValueError("Bad arguments to Packet()");
        else:
            self.v = int(data) & 0xffff
            self.t = PType(t)

    def raw(self):
        return [self.v & 0xff, (self.v >> 8) & 0xff, int(self.t) & 0xff]

    def __str__(self):
        return str(self.raw())


########

def write_packet(dev, packet):
    print '  >>> WRITE ', packet
    dev.write(0x01, packet.raw(), 100)

def read_packet(dev, timeout=2500):   # some responses take awhile
    s = dev.read(0x81, 4, timeout)
    assert(len(s) == 3)
    p = Packet(s)
    print '  <<< READ ', p
    return p

def clear_read_buffer(dev):
    while True:
        try:
            read_packet(dev, timeout=100)
        except:
            break

########

dev = usb.core.find(idVendor=0x3db, idProduct=0x0002)

if dev is None:
    raise ValueError('Device not found')

# dev.set_configuration()
# cfg = dev.get_active_configuration()
# intf = cfg[(0,0)]

# ep = usb.util.find_descriptor(intf,

clear_read_buffer(dev)
write_packet(dev, Packet(0, PType.RESET))
for i in xrange(0, 3):
    write_packet(dev, Packet(0, PType.READ_BLOCK))
    write_packet(dev, Packet(i, PType.READ_BLOCK))
    reply=None
    while reply is None or reply.t != PType.COMPLETE:
        reply = read_packet(dev)

