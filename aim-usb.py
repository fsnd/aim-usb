#!/usr/bin/python2.7 --

import usb.core
import usb.util

class BlockType(object):
    FIRST       = 0x02
    NEXT        = 0x01
    EMPTY       = 0xff


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


class PressureReading(object):
    # FIXME: These don't give the same readings as the Entacore software.
    # Is there a way to get the device itself to output the results again?

    def __init__(self, v):
        self.data = int(v)

    def raw(self):
        return self.data

    def pressure(self):
        """ This function is modeled on a 14-bit linear voltage measurement
        from 0 to 5 volts, measuring the output of a MPXA4115A pressure sensor.

        MPXA's pressure transfer function is:
            Vout = Vs*(.009*P-.095) +- Error
        where:
            Vs = 5.1 VDC
            P is absolute pressure (kPa) relative to a sealed vacuum
        """
        v = float(self.data) / 3276.8
        p = (v/5.1 + .095) / .009
        return p

        return float(self.data)/150.40512 + 95/9

        # return float(self.data)*(3125.0/470016) + 95/9

    def altitude_std(self):
        """ From NOAA: Pressure in millibars -> altitude in feet:
            h = (1-(p/1013.25)^0.190284)*145366.45
        (See Wikipedia: Pressure_altitude)
        """
        p = self.pressure()*10      # 1 kPa = 10 millibar
        h = (1-(p/1013.25)**0.190284)*145366.45
        return h

    def altitude_rel(self, zero):
        return self.altitude_std() - zero.altitude_std()


class FlightEntry(object):
    def __init__(self, pkt):
        if pkt.t != PType.RECORDING_DATA:
            raise ValueError("Expecting a RECORDING_DATA packet")
        self.data = pkt.v
        self.p = PressureReading(self.pressure_raw())

    def lineA(self):
        return bool(self.data & 0x8000)

    def lineB(self):
        return bool(self.data & 0x4000)

    def pressure_raw(self):
        return self.data & 0x3fff

    def pressure(self):
        return self.p.pressure()

    def altitude_std(self):
        return self.p.altitude_std()

    def altitude_rel(self, zero):
        return self.p.altitude_rel(zero)


########

def packetList(t, vals):
    return [Packet(v, t) for v in vals]

def write_packet(dev, packet):
    print '  >>> WRITE ', packet
    dev.write(0x01, packet.raw(), 100)

def read_packet(dev, timeout=2500):   # some responses take awhile
    s = dev.read(0x81, 4, timeout)
    assert(len(s) == 3)
    p = Packet(s)
    # print '  <<< READ ', p
    return p

def clear_read_buffer(dev):
    while True:
        try:
            read_packet(dev, timeout=100)
        except:
            break

def query(dev, packets):
    rs = []
    for p in packets:
        write_packet(dev, p)
    p = None
    while p is None or p.t != PType.COMPLETE:
        p = read_packet(dev)
        rs.append(p)
    return rs

def read_flights(dev):
    flights = []
    f = []
    for bi in xrange(0, 128):
        rs = query(dev, packetList(PType.READ_BLOCK, [0, bi]))
        if rs[0].v & 0xff == BlockType.EMPTY:
            break
        elif rs[0].v & 0xff == BlockType.FIRST:
            if f:
                flights.append(f)
            f = []
        for r in rs[1:-1]:
            if r.v != 0xffff:
                f.append(FlightEntry(r))
    if f is not None:
        flights.append(f)

    return flights


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

flights = read_flights(dev)

for f in flights:
    zero = f[0].altitude_std()
    mn = min(e.altitude_rel(f[0]) for e in f)
    mx = max(e.altitude_rel(f[0]) for e in f)
    print "Zero: {zero:-12.3f}  PZero: {pz:-12.3f}  Min: {mn:-12.3f}  Max: {mx:-12.3f}".format(
            zero=zero, pz=f[0].pressure(), mn=mn, mx=mx)
