#
# DESCRIPTION
#   SDP implementation for communicating with SpiNNaker.  Can be used to make
#   simple servers and clients that can work with programs running on SpiNNaker.
#
# AUTHORS
#   Kier J. Dugan - (kjd1v07@ecs.soton.ac.uk)
#
# DETAILS
#   Created on       : 16 December 2011
#   Revision         : $Revision: 271 $
#   Last modified on : $Date: 2013-02-26 17:10:16 +0000 (Tue, 26 Feb 2013) $
#   Last modified by : $Author: kjd1v07 $
#   $Id: sdp.py 271 2013-02-26 17:10:16Z kjd1v07 $
#
# COPYRIGHT
#   Copyright (c) 2011 The University of Southampton.  All Rights Reserved.
#   Electronics and Electrical Engingeering Group,
#   School of Electronics and Computer Science (ECS)
#

# imports
import struct
import socket
import select


# constants
__all__ = ['SDPMessage', 'SDPConnection']


# exceptions


# classes
class SDPMessage (object):
    """
    Wraps up an SDP message that may be sent or received to/from a SpiNNaker
    using a :py:class:`SDPConnection`.
    
    Typical usage::
    
        conn         = SDPConnection ('fiercebeast2', 17892)
        msg          = SDPMessage ()
        msg.dst_cpu  = 1
        msg.dst_port = 7
        msg.data     = "Hello!"
        conn.send (msg)
        
    Only a small number of fields are used for SDP messages:
    
        ``flags`` (8 bits)
            Amongst other things, determines whether the packet commands a
            response or not
        
        ``tag`` (8 bits)
            IP tag to use, or the IP used.
        
        ``dst_cpu`` (5 bits)
            Target processor on target node (0-17)
        
        ``dst_port`` (3 bits)
            Port on target processor (0-7)
        
        ``src_cpu`` (5 bits)
            Originating processor on source node (0-17)
        
        ``src_port`` (3 bits)
            Port on source processor (0-7)
        
        ``dst_x`` and ``dst_y`` (both 8 bits)
            (X, Y) co-ordinates of target node
        
        ``src_x`` and ``src_y`` (both 8 bits)
            (X, Y) co-ordinates of initiating node
        
        ``data`` (variable length)
            Up to 272 bytes of payload data
    
    .. note::
    
        Although :class:`SDPMessage` is typically used in conjunction with the
        :class:`SDPConnection` class, this is not a requirement.  Calling
        :func:`str` on an :class:`SDPMessage` object will encode the contents
        as a string, and calling :py:meth:`~SDPMessage.from_string` will perform
        the reverse.
    
    """
    
    def __init__ (self, packed=None, **kwargs):
        """
        Constructs a new :py:class:`SDPMessage` object with either default
        values or those provided.
        
        :param packed: encoded packet data
        :type packed:  string or None
        :param kwargs: keyword arguments providing initial values
        
        .. note::
        
            If neither ``packed`` nor ``kwargs`` are provided than internal
            default values will be used.
        
        """
        
        # sizeof(sdp_hdr_t) == 8 in SC&MP/SARK -- used for the size calculation
        self._sizeof_hdr = 8
        
        if packed is not None:
            self.from_string (packed)
        else:
            self.flags    = 0x87
            self.tag      = 0xFF
            self.dst_cpu  =    0
            self.dst_port =    1
            self.src_cpu  =   31
            self.src_port =    7
            self.dst_x    =    0
            self.dst_y    =    0
            self.src_x    =    0
            self.src_y    =    0
            self.data     = ''
        
        # use given values if possible
        if kwargs:
            self.from_dict (kwargs)
    
    def _pack_hdr (self):
        """
        Constructs a string containing *only* the SDP header.
        
        :returns: header encoded as a string
        
        """
        
        # generate source and destination addresses
        src_proc = ((self.src_port & 7) << 5) | (self.src_cpu & 31)
        dst_proc = ((self.dst_port & 7) << 5) | (self.dst_cpu & 31)
        src_addr = ((self.src_x & 0xFF) << 8) | (self.src_y & 0xFF)
        dst_addr = ((self.dst_x & 0xFF) << 8) | (self.dst_y & 0xFF)
        
        # pack the header
        packed = struct.pack ('< 6B 2H', 8, 0, self.flags, self.tag, dst_proc,
            src_proc, dst_addr, src_addr)
        
        return packed
    
    def __str__ (self):
        """
        Constructs a string that can be sent over a network socket using the 
        member variables.
        
        :returns: encoded string
        
        """
        
        # return the full packet
        return self._pack_hdr () + self.data
    
    def __len__ (self):
        """
        Determines the length of the SDP message represented by this class.
        
        :returns: length of the data in this object
        
        """
        
        return self._sizeof_hdr + len (self.data)
    
    def _unpack_hdr (self, packed):
        """
        Reconstructs only an SDP header from ``packed`` and returns what is
        assumed to be payload.
        
        :param str packed: packed data to decode
        :returns:          dictionary of header fields, payload
        
        """
        
        # divide the data into the header and the payload
        pkt, header, payload = {}, packed[:10], packed[10:]
        
        # unpack the header
        (pkt['flags'], pkt['tag'], dst_proc, src_proc, dst_addr,
            src_addr) = struct.unpack ('< 2x 4B 2H', header)
        
        # unmap the tightly packed bits
        pkt['src_port'], pkt['src_cpu'] = src_proc >> 5, src_proc & 0x1F
        pkt['dst_port'], pkt['dst_cpu'] = dst_proc >> 5, dst_proc & 0x1F
        pkt['src_x'],    pkt['src_y']   = src_addr >> 8, src_addr & 0xFF
        pkt['dst_x'],    pkt['dst_y']   = dst_addr >> 8, dst_addr & 0xFF
        
        # return the unpacked header and the payload
        return pkt, payload

    
    def from_string (self, packed):
        """
        Deconstructs the given string and sets the member variables accordingly.
        
        :param str packed: packed data to process
        :raises: :py:class:`struct.error`
        
        """
        
        # unpack the header and the payload
        hdr, payload = self._unpack_hdr (packed)
        
        # merge the fields and store the payload
        self.from_dict (hdr)
        self.data = payload
    
    def from_dict (self, map):
        """
        Updates the SDPMessage object from the given key-value map of valid
        fields.
        
        :param dict map: valid SDP fields
        
        """
        
        for k, v in map.iteritems ():
            setattr (self, k, v)


class SDPConnection (object):
    """
    Represents an SDP connection to a target SpiNNaker machine or an incoming
    SDP connection to the local machine.
    
    Typical usage::
    
        conn = SDPConnection ('fiercebeast2')
        msg  = SDPMessage ()
        msg.dst_cpu  = 1
        msg.dst_port = 7
        msg.data     = "Hello!"
        conn.send (msg)
        conn.wait_for_message ()
        response = conn.receive ()
    
    It is also to use this connection to set up an SDP server that can respond
    to incoming SDP connections over the network::
    
        with SDPConnection ('localhost') as conn:
            messages = 0
            conn.listen (0.2) # wait for message for 0.2s or return None
            for msg in conn:
                if msg:
                    print msg.data
                    messages += 1
                elif messages >= 100: # stop after 100 messages
                    conn.interrupt ()
    
    The above example demonstrates two key features implemented by
    :py:class:`SDPConnection`.  It can be iterated over using a ``for``-loop
    which will return either a valid message or ``None`` if
    :py:data:`iterator_timeout` has elapsed.  This allows the application to
    perform behaviours even if a packet has not yet arrived, which is stopping
    the iteration with :py:meth:`interrupt` in the case of the example above.
    
    :py:class:`SDPConnection` also implements a *context manager* which allows
    it to be used as part of a ``with`` clause.  Clean-up is automatic if this
    method is used and is hence useful when implementing servers.
    
    .. note::
    
        Clean-up is *still* automatic when using a ``with`` statement, even if
        an exception is raised in the code because Python ensures that context
        managers are informed of *all* changes of context regardless of the
        cause.
    
    .. seealso::
    
        - :py:class:`SDPMessage`
        - :py:class:`SCPMessage`
        - :py:class:`SCPConnection`
    
    """
    
    def __init__ (self, host='fiercebeast0', port=17893):
        """
        Constructs a :py:class:`SDPConnection` object.
        
        :param str host: hostname of the target (or host if listening)
        :param int port: port to send to (or one which to listen)
        :raises:         ValueError
        
        """
        
        self._sock = None

        # resolve the hostname to make things easier
        try:
            # resolving 'locahost' will find the correct hostname but will
            # *always* return an IP of 127.0.0.1 which seems to prevent external
            # connections under some conditions.
            if host.lower () in ('localhost', '127.0.0.1'):
                host = socket.gethostname ()
            
            hostname, _, addresses = socket.gethostbyname_ex (host)
        except:
            raise ValueError ('cannot resolve hostname %s' % host)

        # store the hostname and the host IP for messages
        self._hostname  = hostname
        self._host      = addresses[0]
        self._port      = port    
        self._addr      = (self._host, port)
        self._interrupt = True
        self._iter_to   = None
        
        # create a socket and enforce a small timeout
        self._sock = socket.socket (socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout (1.0) # 1 second
    
    def __del__ (self):
        """
        Class destructor -- closes any open network connections.
        
        """
        
        self.close ()
    
    def __enter__ (self):
        """
        Context manager -- enter new context.
        
        There is no special behaviour required here because the network socket
        is established in the class constructor.
        
        """
        
        return self
    
    def __exit__ (self, type, value, traceback):
        """
        Context manager -- leave existing context.
        
        :param type:      type of the exception
        :param value:     instance value of the exception
        :param traceback: stack trace up until the error
        
        Special behaviour *may* be required here depending on the exception
        raised.  A :py:exc:`StopIteration` may be suppressed as this is the
        desired use case, but all other exceptions are probably genuine errors
        that the user should care about.
        
        """
        
        # close down the socket
        self.close ()
        
        # context managers may return True to suppress an exception or anything
        # that will evaluate to False to allow it to propagate.  They must
        # *never* raise exceptions unless they themselves have failed.
        return type is StopIteration
    
    remote_hostname = property (fget=lambda self: self._hostname,
        doc="Hostname of the remote SpiNNaker")
    
    remote_host_ip = property (fget=lambda self: self._host,
        doc="IPv4 address of the remote SpiNNaker")
    
    remote_host_port = property (fget=lambda self: self._port,
        doc="Port to connect to on the remote SpiNNaker")
    
    def __repr__ (self):
        """
        Custom representation for interactive programming.
        
        :return: string 
        
        """
        
        return 'SDPConnection: {:s}[{:s}]:{:d}'.format (self.remote_hostname,
            self.remote_host_ip, self.remote_host_port)
        
    def send (self, message):
        """
        Sends an :py:class:`SDPMessage` to the remote host.
        
        :param SDPMessage message: message packet to send
        :raises: socket.error, socket.timeout, struct.error
        
        """
        
        raw_data = str (message)
        self._sock.sendto (raw_data, self._addr)
    
    def receive (self, msg_type=SDPMessage):
        """
        Recives data from the remote host and processes it into the required
        object type (default is :py:class:`SDPMessage`).
        
        :param msg_type: :py:class:`SDPMessage`-derived class to unpack response
        :raises: socket.error, socket.timeout, struct.error
        
        """
        
        raw_data, addr = self._sock.recvfrom (512)
        return msg_type (raw_data)
    
    def has_message (self, timeout=0):
        """
        Returns ``True`` if there is a message in the buffer that should be
        handled.
        
        :param timeout: maximum time (in seconds) to wait before returning
        :type timeout:  float or None
        
        """
        
        rlist, wlist, xlist = select.select ([self._sock], [], [], timeout)
        
        return self._sock in rlist
    
    def __nonzero__ (self):
        """
        Returns ``True`` if there is a message in the buffer.
        
        """
        
        return self.has_message ()
    
    def wait_for_message (self):
        """
        Spins indefinitely waiting for an :py:class:`SDPMessage` to arrive.
        
        """
        
        while True:
            if self.has_message (0.2):
                return
    
    def __iter__ (self):
        """
        Returns an instance of an interator object for this class.
        
        """
        
        return _SDPConnectionIterator (self)
    
    def listen (self, timeout=None):
        """
        Binds the current socket to the hostname and port number given in the
        constructor so that messages may be delivered to this object.  This
        process can be stopped by calling either :py:meth:`interrupt` or
        :py:meth:`stop`.
        
        :param float timeout: seconds to wait for a packet or ``None``
        
        Usage::
        
            with SDPConnection ('localhost') as conn:
                conn.listen ()
                for msg in conn:
                    print msg.data
        
        An optional timeout may be specified which is the maximum number of 
        seconds the iterator will wait for a packet.  If no packet arrives in
        this interval then the iterator will return ``None`` which allows the
        loop to do useful work between packet arrivals.  If ``timeout`` is
        ``None`` (the default value) then each wait will block indefinitely.  
        
        .. seealso::
        
            :py:meth:`interrupt`
        
        """
        
        # allow the iterator to run
        self._interrupt = False
        self._iter_to   = timeout
        
        # bind the socket to the given port
        self._sock.bind ((self._host, self._port))
    
    def close (self):
        """
        Closes the internal socket.
        
        """
        
        if self._sock:
            self._sock.close ()
            self._sock = None
    
    def interrupt (self):
        """
        Stops the current iteration over the connection.
        
        """
        
        self._interrupt = True
    
    def _next (self):
        """
        Private function that actually performs the iterator behaviour for
        :py:class:`_SDPConnectionIterator`.
        
        """
        
        if self._interrupt is True:
            raise StopIteration
        
        if self.has_message (self._iter_to):
            return self.receive ()
        else:
            return None


# functions


# private classes
class _SDPConnectionIterator (object):
    """
    Iterator object that waits for messages on a :py:class:`SDPConnection`.
    
    """

    def __init__ (self, conn):
        """
        Construct an _SDPConnectionIterator object for the given SDPConnection.
        
        :param conn: :py:class:`SDPConnection` to iterate over
        
        """
        
        self._conn = conn
    
    def next (self):
        """
        Returns the next packet in the SDP stream.
        
        :returns: next :py:class:`SDPMessage` in the stream or ``None``
        
        """
        
        return self._conn._next ()

# private functions


