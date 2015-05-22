#!/usr/bin/python2.7 --

import usb.core
import usb.util

dev = usb.core.find(idVendor=0x3db, idProduct=0x0002)

if dev is None:
    raise ValueError('Device not found')

# dev.set_configuration()
# cfg = dev.get_active_configuration()
# intf = cfg[(0,0)]

# ep = usb.util.find_descriptor(intf,

still=True
while still:
    try:
        dev.read(0x81, 5, 100)
    except:
        still=False

dev.write(0x01, '\x00\x00\x01', 100)
dev.write(0x01, '\x00\x00\x08', 100)
reply=None
while reply is None or reply[2] != 0x05:
    reply = dev.read(0x81, 5, 2500)     # some responses take awhile
    print ' '.join('{0:02x}'.format(b) for b in reply)


