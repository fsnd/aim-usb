#!/usr/bin/python3.4 --

import usb.core
import usb.util
from enum import Enum


class LineMode(Enum):
    DISABLE     = 0
    TIME        = 1
    APOGEE      = 2
    ALTITUDE    = 3
    ASCEND_ALTI = 4


class BlockType(Enum):
    FIRST       = 0x02
    NEXT        = 0x01
    EMPTY       = 0xff


class PType(Enum):
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
        return [self.v & 0xff, (self.v >> 8) & 0xff, self.t.value & 0xff]

    def __str__(self):
        return str(self.raw())


class PressureReading(object):
    # TODO: Allow selecting of imperial or metric units

    def __init__(self, v, adcOffset=0):
        self.data = int(v)
        self.offset = adcOffset

    def raw(self):
        return self.data

    def voltage(self):
        v = float(self.data + self.offset) / 3276.8
        return v

    def pressure(self):
        """ This function is modeled on a 14-bit linear voltage measurement
        from 0 to 5 volts, measuring the output of a MPXA4115A pressure sensor.

        MPXA4115A's pressure transfer function is:
            Vout = Vs*(.009*P-.095) +- Error
        where:
            Vs = 5.1 VDC +- 0.25    (nominally, and in this usage exactly 5.0 VDC)
            P is absolute pressure (kPa) relative to a sealed vacuum
        """
        p = (self.voltage()/5.0 + .095) / .009
        return p

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


class FlightSample(object):
    def __init__(self, pkt, adcOffset=0):
        if pkt.t != PType.RECORDING_DATA:
            raise ValueError("Expecting a RECORDING_DATA packet")
        self.data = pkt.v
        self.p = PressureReading(self.pressure_raw(), adcOffset=adcOffset)

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


class AltimeterSettings(object):
    def __init__(self, packets):
        if not (len(packets) == 18 or
                (len(packets) == 19 and packets[18].t == PType.COMPLETE)):
            raise ValueError("Expecting 18 DATA packets")
        cksum = ((packets[17].v<<8) + packets[16].v) & 0xffff
        pktsum = (sum(p.v for p in packets[:16]) + 120) & 0xffff
        if cksum != pktsum:
            raise ValueError("Checksum failed: {0} != {1}".format(pktsum, cksum))

        p = packets
        self.maxSamples         = self._u16le(p[0:2])
        self.autoStopEnable     = bool(p[2].v & 1)
        self.launchDetectM      = self._u16le(p[3:5])
        self.machInhibitDS      = self._u16le(p[5:7])
        self.batMinDV           = self._u8(p[7:8])
        self.adcOffset          = self._s16le(p[8:10])
        self.lineAMode          = LineMode( self._u8(p[10:11]) & 0x0f )
        self.lineBMode          = LineMode( (self._u8(p[10:11]) >> 4) & 0x0f )
        self.lineAThreshold     = self._u16le(p[11:13])     # altitude(m) or delay(ds)
        self.lineBThreshold     = self._u16le(p[13:15])     # altitude(m) or delay(ds)
        self.beepImperial       = bool(p[15].v & 1)

    def _u8(self, bs):
        return (bs[0].v & 0xff)

    def _s16le(self, bs):
        u = self._u16le(bs)
        return (u ^ 0x8000) - 0x8000

    def _u16le(self, bs):
        return ((bs[0].v & 0xff) + (bs[1].v << 8)) & 0xffff

    def _pack_16le(self, v):
        return [v & 0xff, (v >> 8) & 0xff]

    def _pack_8(self, v):
        return [v & 0xff]

    def raw(self):
        vs = []
        vs.extend(self._pack_16le(self.maxSamples))
        vs.extend(self._pack_8(-self.autoStopEnable))
        vs.extend(self._pack_16le(self.launchDetectM))
        vs.extend(self._pack_16le(self.machInhibitDS))
        vs.extend(self._pack_8(self.batMinDV))
        vs.extend(self._pack_16le(self.adcOffset))
        vs.extend(self._pack_8((self.lineAMode.value & 0xf) +
                               ((self.lineBMode.value & 0xf) << 4)))
        vs.extend(self._pack_16le(self.lineAThreshold))
        vs.extend(self._pack_16le(self.lineBThreshold))
        vs.extend(self._pack_8(-self.beepImperial))
        pktsum = (sum(vs) + 120) & 0xffff
        vs.extend(self._pack_16le(pktsum))
        return [Packet(v, PType.DATA) for v in vs]

    def __str__(self):
        return self.__dict__.__str__()


class Altimeter(object):
    def __init__(self, usb_dev):
        self._dev = usb_dev
        self._settings = None

    def settings(self, refresh=False):
        if refresh or self._settings is None:
            rs = query(self._dev, (Packet(0, PType.READ_SETTINGS),))
            self._settings = AltimeterSettings(rs)

            # FIXME: Better logging, and/or move to a test case
            ssrs = self._settings.raw()
            if len(rs) != len(ssrs)+1:
                print("LENGTHS DIFFER: {0} {1}".format(len(rs), len(ssrs)))
            for i in range(len(ssrs)):
                if rs[i].v != ssrs[i].v:
                    print("BYTE {0} DIFFERS: {1} {2}".format(i, rs[i], ssrs[i]))

        return self._settings


########

# TODO: Move most or all of these into the Altimeter object

def packetList(t, vals):
    return [Packet(v, t) for v in vals]

def write_packet(dev, packet):
    print('  >>> WRITE {0}'.format(packet))
    dev.write(0x01, packet.raw(), 100)

def read_packet(dev, timeout=2500):   # some responses take awhile
    s = dev.read(0x81, 4, timeout)
    assert(len(s) == 3)
    p = Packet(s)
    # print('  <<< READ {0}'.format(p))
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

def read_flights(alti):
    flights = []
    f = []
    for bi in range(0, 128):
        rs = query(alti.dev, packetList(PType.READ_BLOCK, [0, bi]))
        if BlockType(rs[0].v & 0xff) == BlockType.EMPTY:
            break
        elif BlockType(rs[0].v & 0xff) == BlockType.FIRST:
            if f:
                flights.append(f)
            f = []
        for r in rs[1:-1]:
            if r.v != 0xffff:
                f.append(FlightSample(r, adcOffset=alti.settings().adcOffset))
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

alti = Altimeter(dev)
alti.settings()

# flights = []
flights = read_flights(alti)

for f in flights:
#    for e in f:
#        print("Raw: {0}   Voltage: {1}   Pressure: {2}   Alti: {3}".format(
#                e.p.raw(), e.p.voltage(), e.p.pressure(), e.p.altitude_std()))
    zero = f[0].altitude_std()
    mn = min(e.altitude_rel(f[0]) for e in f)
    mx = max(e.altitude_rel(f[0]) for e in f)
    print("Zero: {zero:-12.3f}  PZero: {pz:-12.3f}  Min: {mn:-12.3f}  Max: {mx:-12.3f}".format(
            zero=zero, pz=f[0].pressure(), mn=mn, mx=mx))
