#!/usr/bin/env python
"""
A tool for displaying images on SpiNNaker board LEDs.
"""

import copy
import struct
import time

import spinn_blink.scp as scp

class SpiNNakerBoard(object):
	"""
	A spinnaker board which can be driven like a display.
	"""
	
	SDRAM_BASE_UNBUF = 0x70000000
	SDRAM_OFFSET = 0x00000000
	
	def __init__(self, system_size, resolution, hostname):
		"""
		Use a single SpiNNaker board as an LED matrix.
		
		Legit.
		"""
		self.fail_count = 0
		self.fail_thres = 10
		
		self.system_size = system_size
		self.resolution = resolution
		
		# Connect to the board
		self.conn = scp.SCPConnection(hostname)
		
		# Test the connection
		self.conn.version()
		
		# Which chips are enabled/present (default to all of them)
		self.enabled_chips = [[True]*system_size[0] for _ in range(system_size[1])]
		
		# A mapping from chips to the system size, should be defined by a subclass
		self.pos_to_chip = [[(0,0)]*resolution[0] for _ in range(resolution[1])]
		
		# Create a display buffer where each pixel is a chip position
		self._display_buffer = [[0]*system_size[0] for _ in range(system_size[1])]
	
	
	def update_display(self):
		"""
		Send the current display buffer to the LEDs in the system
		"""
		for y, row_data in enumerate(self._display_buffer):
			for x, pixel in enumerate(row_data):
				if self.enabled_chips[y][x]:
					try:
						self.conn.selected_cpu_coords = (x,y,0)
						display_data = struct.pack("I", int(255.0*pixel))
						self.conn.write_mem(self.SDRAM_BASE_UNBUF + self.SDRAM_OFFSET, scp.TYPE_WORD, display_data)
					except:
						self.fail_count += 1
						time.sleep(0.1)
						if self.fail_count > self.fail_thres:
							raise
	
	
	@property
	def display_buffer(self):
		out = [[0]*len(pos_to_chip[0]) for _ in range(len(pos_to_chip))]
		for y in range(len(pos_to_chip)):
			for x in range(len(pos_to_chip[0])):
				x_,y_ = self.pos_to_chip[y][x]
				out[y][x] = self._display_buffer[y_][x_]
		return out
	
	
	@display_buffer.setter
	def display_buffer(self, value):
		for y, row_data in enumerate(value):
			for x, pixel in enumerate(row_data):
				x_,y_ = self.pos_to_chip[y][x]
				self._display_buffer[y_][x_] = pixel


class SpiNN3Board(SpiNNakerBoard):
	"""
	A Spin-5 board style SpiNNaker board with 48 chips arranged oddly.
	"""
	
	def __init__(self, hostname):
		SpiNNakerBoard.__init__(self, (2,2), (4,1), hostname)
		
		self.pos_to_chip = [[(0,0),(0,1),(1,0),(1,1)]]


class SpiNN5Board(SpiNNakerBoard):
	"""
	A Spin-5 board style SpiNNaker board with 48 chips arranged oddly.
	"""
	
	def __init__(self, hostname):
		SpiNNakerBoard.__init__(self, (8,8), (7,7), hostname)
		
		# The chips which exist on such a board self.enabled_chips[y][x]
		self.enabled_chips = [
			[False,False,False,False,True ,True ,True ,True ],
			[False,False,False,True ,True ,True ,True ,True ],
			[False,False,True ,True ,True ,True ,True ,True ],
			[False,True ,True ,True ,True ,True ,True ,True ],
			[True ,True ,True ,True ,True ,True ,True ,True ],
			[True ,True ,True ,True ,True ,True ,True ,False],
			[True ,True ,True ,True ,True ,True ,False,False],
			[True ,True ,True ,True ,True ,False,False,False],
		][::-1]
		
		# A mapping from a pixel position to a chip coordinate (note that the
		# missing pixel is assigned to a core which doesn't exist: 7,0)
		self.pos_to_chip = [
			[(2,5),(3,6),(4,7),(5,7),(5,6),(6,7),(7,0)],
			[(1,4),(3,5),(4,5),(4,6),(5,5),(6,6),(7,7)],
			[(0,3),(2,4),(3,4),(4,4),(5,4),(6,5),(7,6)],
			[(1,3),(2,3),(3,3),(4,3),(5,3),(6,4),(7,5)],
			[(0,2),(1,2),(2,2),(3,2),(4,2),(6,3),(7,4)],
			[(0,1),(1,1),(2,1),(3,1),(4,1),(5,2),(7,3)],
			[(0,0),(1,0),(2,0),(3,0),(4,0),(5,1),(6,2)],
		][::-1]



if __name__=="__main__":
	"""
	Example: As a command-line app, takes a hostname for a spinn5 board and an
	image file to scroll.
	"""
	import sys
	import time
	from PIL import Image
	
	b = SpiNN5Board(sys.argv[1])
	msg = Image.open(sys.argv[2])
	while True:
		for i in range(msg.size[0]-7):
			b.display_buffer = [[ msg.getpixel((x+i, 6-y))[0] for x in range(7) ][::-1] for y in range(7)]
			b.update_display()
			time.sleep(0.10)
