#!/usr/bin/env python

"""
Example: As a command-line app, takes a hostname for a spinn5 board and an
image file to scroll.
"""

import sys
import time

from PIL import Image

from spinn_blink import SpiNN5Board

b = SpiNN5Board(sys.argv[1])
msg = Image.open(sys.argv[2])

while True:
	for i in range(msg.size[0]-7):
		b.display_buffer = [[ msg.getpixel((x+i, 6-y))[0] for x in range(7) ][::-1] for y in range(7)]
		b.update_display()
		time.sleep(0.10)
