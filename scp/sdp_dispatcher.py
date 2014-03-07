"""
SDP Dispatcher
"""

import threading

class SDPDispatcher( object ):
    """An SDP Dispatcher handles the regular transmission of SDP Packets to a
    SpiNNaker machine.  This is done to ensure that overloading of the root
    processor will not occur.

    :param connection: a connection to the SpiNNaker machine
    :param delay: inter-packet transmission delay (default = 0.0005 seconds)
    """
    def __init__( self, connection, delay = 0.0005 ):
        self._queue = []
        self._queue_lock = threading.Lock()

        self._halt = False
        self._delay = delay

        self._conn = connection

    def start( self ):
        """Start the Dispatcher."""
        self._timer = threading.Timer( self._delay, self.tick )
        self._timer.start( )

    def stop( self ):
        """Stop the Dispatcher."""
        self._timer.cancel()
        self._halt = True

    def queue_packet( self, packet ):
        """Add a new packet to the queue."""
        with self._queue_lock:
            self._queue.append( packet )

    def tick( self ):
        with self._queue_lock:
            if not len( self._queue ) == 0:
                self._conn.send( self._queue.pop( 0 ) )

        if not self._halt:
            self.start( )
