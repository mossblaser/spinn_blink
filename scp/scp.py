#
# DESCRIPTION
#   A simple implementation of the SpiNNaker command protocol.
#
# AUTHORS
#   Kier J. Dugan - (kjd1v07@ecs.soton.ac.uk)
#
# DETAILS
#   Created on       : 11 May 2012
#   Revision         : $Revision: 271 $
#   Last modified on : $Date: 2013-02-26 17:10:16 +0000 (Tue, 26 Feb 2013) $
#   Last modified by : $Author: kjd1v07 $
#   $Id: scp.py 271 2013-02-26 17:10:16Z kjd1v07 $
#
# COPYRIGHT
#   Copyright (c) 2012 The University of Southampton.  All Rights Reserved.
#   Electronics and Electrical Engingeering Group,
#   School of Electronics and Computer Science (ECS)
#

# imports
import array
import math
import os
import select
import socket
import struct
import time

import legacy
import scamp
import sdp


# constants
__all__ = ['SCPConnection', 'SCPMessage', 'SCPError']


# exceptions
class SCPError (RuntimeError):
    """
    Error response from target SpiNNaker.
    
    :param int rc: response code from target SpiNNaker.
    :param msg: :py:class:`SCPMessage` that caused the error or ``None``
    
    """
    
    def __init__ (self, rc, msg=None):
        """
        Construct an :py:exc:`SCPError` object.
        
        """
        
        # get a nice custom error message
        super (SCPError, self).__init__ (
            "command failed with error %s: '%s'" % scamp.rc_to_string (rc))

        # save the response code
        self.rc      = rc
        self.rc_text = scamp.rc_to_string (rc)
        self.message = msg


class SCPMessage (sdp.SDPMessage):
    """
    Builds on :py:class:`SDPMessage` by adding the following fields to support
    SCP messages:
    
        ``cmd_rc`` (16 bits)
            *command* on outgoing packets and *response code* on incoming
            packets
        
        ``seq`` (16 bits)
            sequence code -- not used for every command type
        
        ``arg1``, ``arg2``, ``arg3`` (all 32 bits)
            optional word data at the start of the payload that may be ignored
            if ``raw_data`` is used directly
        
        ``payload`` (variable length)
            optional data field that appears *after* the optional arguments in
            the SCP payload
        
        ``data`` (variable length)
            SCP packet payload *including* the optional word data fieelds.
        
        ``has_args`` (boolean)
            indicates whether the word data fields are used or not
    
    Usage::
        
        conn         = SCPConnection ('fiercebeast2')
        msg          = SCPMessage ()
        msg.cmd_rc   = scamp.CMD_VER
        msg.has_args = False
        response     = conn.send (msg)
        
    .. seealso::
    
        - :py:class:`SCPConnection`
        - :py:class:`SDPConnection`
        - :py:class:`SDPMessage`
    
    """
    
    def __init__ (self, packed=None, **kwargs):
        """
        Contructs a new :py:class:`SCPMessage` object -- overloaded from base
        class to add new members.
        
        :param packed: encoded packet data
        :type packed:  string or None
        :param kwargs: keyword arguments providing initial values
        
        """
        
        # (sizeof(sdp_hdr_t) + 2*sizeof(uint16_t) == 12 in SC&MP/SARK -- used
        # for the size calculation
        self._sizeof_hdr = 12
        
        # call base class
        super (SCPMessage, self).__init__ ()
        
        # default initialise new members before calling the base constructor
        self.dst_port = 0  # override from base class for command port
        self.cmd_rc   = 0
        self.seq      = 0
        self.arg1     = 0
        self.arg2     = 0
        self.arg3     = 0
        self.payload  = ''
        self.data     = ''
        self.has_args = True
        
        # handle the packed data and keyword arguments after default init
        if packed is not None:
            self.from_string (packed)
        if kwargs:
            self.from_dict (kwargs)
    
    def _pack_hdr (self):
        """
        Overloaded from base class to pack the extra header fields.
        
        """
        
        # pack the two compulsory SCP fields and append them to the SDP header
        scp_packed = struct.pack ('<2H', self.cmd_rc, self.seq)
        
        return super (SCPMessage, self)._pack_hdr () + scp_packed
    
    def _unpack_hdr (self, packed):
        """
        Overloaded from base class to unpack the extra header fields.
        
        :param str packed: encoded string
        
        """
        
        # get the SDP header from the base class
        pkt, payload = super (SCPMessage, self)._unpack_hdr (packed)
        
        # strip 4 bytes from the payload to decode the SCP compulsory fields
        scp_hdr, payload = payload[:4], payload[4:]
        (pkt['cmd_rc'], pkt['seq']) = struct.unpack ('<2H', scp_hdr)
        
        return pkt, payload
    
    @property
    def arg1 (self):
        """
        Optional integer argument 1.
        
        """
        
        return self._arg1
    
    @arg1.setter
    def arg1 (self, value):
        self._arg1    = value
        self.has_args = True
    
    @property
    def arg2 (self):
        """
        Optional integer argument 2.
        
        """
        
        return self._arg2
    
    @arg2.setter
    def arg2 (self, value):
        self._arg2    = value
        self.has_args = True
    
    @property
    def arg3 (self):
        """
        Optional integer argument 3.
        
        """
        
        return self._arg3
    
    @arg3.setter
    def arg3 (self, value):
        self._arg3    = value
        self.has_args = True
    
    @property
    def data (self):
        """
        Optional payload for the :py:class:`SCPMessage` object -- automatically
        packs the word arguments and variable-length data into a single value.
        
        """
        
        if self.has_args:
            _data  = struct.pack ('<3I', self.arg1, self.arg2, self.arg3)
            _data += self.payload
        else:
            _data = self._data
        
        return _data
    
    @data.setter
    def data (self, value):
        """
        Optional payload for the message -- automatically unpacks the word
        arguments if there is sufficient space to do so.
        
        :param str value: payload to unpack
        
        """
        
        if len (value) >= 12:
            self.has_args = True
            (self.arg1, self.arg2, self.arg3) = struct.unpack ('<3I',
                value[:12])
            self.payload = value[12:]
        else:
            self.has_args = False
            self._data = value


# class that wraps up the SCP protocol
class SCPConnection (sdp.SDPConnection):
    """
    Builds on an :py:class:`SDPConnection` to support the SpiNNaker Command
    Protocol (SCP) which can interact with SC&MP and SARK.
    
    Example usage::
    
        conn = SCPConnection ('fiercebeast2', 17893)
        conn.select ('root')
        conn.set_iptag (0, 'localhost', 34521)
        conn.select (1)
        conn.write_mem_from_file (0x78000000, TYPE_WORD, 'myapp.aplx')
        conn.exec_aplx (0x78000000)
    
    It is possible to send user-specific :py:class:`SCPMessage`\ s if the target
    application uses the SCP packet format by simplying using the
    :py:meth:`send` and :py:meth:`receive` methods with :py:class:`SCPMessage`
    objects instead of :py:class:`SDPMessage`.  This class overrides both
    methods to ensure that this works correctly, which means that the *context
    manager* and *iterator* behaviours of :py:class:`SDPConnection` are
    automatically supported by :py:class:`SCPConnection`.
    
    .. note::
    
        :py:class:`SCPConnection` maintains an internal record of a *selected*
        processor and hence any :py:class:`SCPMessage`\ s sent will have their
        target members changed to reflect this internal record.
    
    .. seealso::
    
        - :py:class:`SCPMessage`
        - :py:class:`SDPConnection`
        - :py:class:`SDPMessage`
    
    """
    
    def __init__ (self, host='fiercebeast0', port=17893):
        """
        Constructs a new :py:class:`SCPConnection` object.
        
        :param str host: hostname of the remote SpiNNaker machine
        :param int port: port number to communicate through
        
        """
        
        # construct a normal SDP connection
        super (SCPConnection, self).__init__ (host, port)
        
        # intialise SCP members
        self._x     = 0
        self._y     = 0
        self._cpu   = 0
        self._node  = (self._x << 8) | self._y
        
        # initialise the sequence number counter
        self._seq = 0
    
    def __repr__ (self):
        """
        Custom representation for interactive programming -- overridden from
        SDPConnection.
        
        :return: string 
        
        """
        
        return 'SCPConnection: {:s}[{:s}]:{:d}'.format (self.remote_hostname,
            self.remote_host_ip, self.remote_host_port)
    
    def select (self, *args):
        """
        Select the target node and processor.
        
        :param args: variadic argument (usage below)
        :raises:     ValueError
        
        This function has the following calling conventions:
        
            ``conn.select ('root')``
                Short-hand to select node (0, 0, 0)
            
            ``conn.select (N)``
                Selects processor N on the currently selected node
            
            ``conn.select (X, Y)``
                Selects processor 0 on node (``X``, ``Y``)
            
            ``conn.select (X, Y, N)``
                Selects processor ``N`` on node (``X``, ``Y``)
        
        """
        
        # extract the arguments
        if len (args) == 1 and type (args[0]) == str and args[0] == "root":
            (x, y, cpu) = (0, 0, 0)
        elif len (args) == 1 and type (args[0]) == int:
            (x, y, cpu) = (self._x, self._y, args[0])
        elif len (args) == 2:
            (x, y, cpu) = (args[0], args[1], 0)
        elif len (args) == 3:
            (x, y, cpu) = args
        else:
            raise ValueError ("invalid arguments given for SCPConnection."
                "select call.")
        
        # make sure that the variables are all ints
        if type (x) != int or type (y) != int or type (cpu) != int:
            raise ValueError ("invalid argument types given expecting ints or "
                "a single string 'root'.")
        
        # save the variables
        self._x     = x & 0xFF
        self._y     = y & 0xFF
        self._cpu   = cpu
        self._node  = (self._x << 8) | self._y
    
    @property
    def selected_node_coords (self):
        """
        (X, Y) co-ordinates of the selected node in P2P space.
        
        """
        
        return (self._x, self._y)
    
    @selected_node_coords.setter
    def selected_node_coords (self, new_coords):
        (self._x, self._y) = new_coords
        self._node         = ((self._x & 0xFF) << 8) | (self._y & 0xFF)
    
    @property
    def selected_node (self):
        """
        Node P2P ID comprised of X|Y co-ordinates.
        
        """
        
        return self._node
    
    @selected_node.setter
    def selected_node (self, new_id):
        self._node = new_id
        (self._x, self._y) = ((new_id >> 8) & 0xFF, new_id & 0xFF)
    
    @property
    def selected_cpu (self):
        """
        Index of the selected CPU on the selected node.
        
        """
        
        return self._cpu
    
    @selected_cpu.setter
    def selected_cpu (self, new_cpu):
        self._cpu = new_cpu
    
    @property
    def selected_cpu_coords (self):
        """
        (X, Y, N) co-ordinates of the selected CPU (N) and node (X, Y).
        
        """
        
        return (self._x, self._y, self._cpu)
    
    @selected_cpu_coords.setter
    def selected_cpu_coords (self, new_coords):
        (self._x, self._y, self._cpu) = new_coords
        self._node = ((self._x & 0xFF) << 8) | (self._y & 0xFF)
    
    def receive (self, msg_type=SCPMessage):
        """
        Override from :py:class:`SDPConnection` to convert the socket data into
        an :py:class:`SCPMessage` object (or whichever is required).
        
        :param msg_type: :py:class:`SCPMessage`-derived class to unpack response
        :raises: socket.error, socket.timeout, struct.error
        
        """
        
        return super (SCPConnection, self).receive (msg_type)
    
    def send_scp_msg (self, msg):
        """
        Dispatches the given packet and expects a response from the target
        machine.  Before the packet is sent, the destination co-ordinates and
        CPU index are altered to match the values internal to this class.
        
        :param SCPMessage msg: command packet to send to remote host
        :returns: :py:class:`SCPMessage` returned from the remote host
        :raises: SCPError
        
        """
        
        # update the message before sending
        msg.dst_cpu = self._cpu
        msg.dst_x   = self._x
        msg.dst_y   = self._y
        
        # get the response from the remote host
        sentMessage = False
        retries = 10;
        while sentMessage == False and retries > 0:
            try:
                self.send (msg)
                resp = self.receive ()
                if (resp.cmd_rc != scamp.RC_TIMEOUT):                
                    sentMessage = True;
                else:
                    print "Warning - response was RC_TIMEOUT, retrying"
                    retries -= 1
            except socket.timeout as e:
                print "Warning - timeout waiting for response"
                retries -= 1
        if sentMessage == False:
            raise SCPError(0, "Failed to receive response after sending message")
        
        # deal with errors by making it someone else's problem!
        if resp.cmd_rc != scamp.RC_OK:
            raise SCPError (resp.cmd_rc, resp)
        else:
            return resp
    
    def version (self):
        """
        Retreives the version information about the host operating system.
        
        :returns: version of OS in a class
        :raises:  SCPError
        
        """
        
        cmd_msg = SCPMessage (cmd_rc=scamp.CMD_VER)
        ver_msg = self.send_scp_msg (cmd_msg)
        
        # decode the payload into a usable struct
        return VersionInfo (ver_msg)
    
    def _next_seq_num (self):
        """
        Generate a new sequence number for some of the SC&MP/SARK commands.
        
        :returns: int -- next sequence number
        
        """
        
        # mod 128 counter increment
        self._seq = (self._seq + 1) % 128
        return (2 * self._seq)
    
    def init_p2p_tables (self, cx, cy):
        """
        Configure the P2P tables on the remote SpiNNaker using the Manchester
        algorithm which superimposes a 2D co-ordinate space on the SpiNNaker
        fabric.
        
        :param int cx: width of the P2P space
        :param int cy: height of the P2P space
        
        """
        
        msg = SCPMessage (cmd_rc=scamp.CMD_P2PC)
        
        # generate a new sequence number
        seq = self._next_seq_num ()
        
        # the following lines have been taken almost verbatim from ybug.
        # the comments state the following organisation but this is clearly no
        # longer the case:
        #   arg1 = 00 : 00 :   00   : seq num
        #   arg2 = cx : cy : addr x : addr y
        #   arg3 = 00 : 00 :   fwd  :  retry
        msg.arg1 = (0x003e << 16) | seq
        msg.arg2 = (cx << 24) | (cy << 16)
        msg.arg3 = 0x3ff8
        
        # send the command to SpiNNaker
        self.send_scp_msg (msg)

    def get_iptag_table_info (self):
        """
        Retrieve the number of fixed and transient tags available as well as
        the default timeout for all transient tags.
        
        :returns: fixed record count, transient record count, default timeout
        :raises:  SCPError
        
        """
        
        # build up the request according to the following formula:
        #   arg1 = 0 : command : 0 :    0
        #   arg2 = 0 :    0    : 0 : timeout
        #   arg3 = 0 :    0    : 0 :    0
        msg        = SCPMessage ()
        msg.cmd_rc = scamp.CMD_IPTAG
        msg.arg1   = scamp.IPTAG_TTO << 16
        msg.arg2   = 255                  # must be 16 or greater to be ignored
        msg.arg3   = 0
        resp_msg   = self.send_scp_msg (msg)
        
        # decode the response data (32bits) structured as follows:
        #   31:24 - max. number of fixed tags
        #   23:16 - max. number of transient tags
        #   15: 8 - reserved (0)
        #    7: 0 - transient timeout exponent
        if len (resp_msg.data) != 4:
            raise ValueError ("insufficient data received in response.")
        (ttoE, trans, fixed) =  struct.unpack ('Bx2B', resp_msg.data)
        
        # convert the timeout into seconds using the equation:
        #    timeout = 10ms * 2^(ttoE - 1)
        timeout = (1 << (ttoE - 1)) * 0.01
        
        return (fixed, trans, timeout)
    
    def set_transient_iptag_timeout (self, timeout):
        """
        Sets the timeout for all transient IP-tags on the target machine.
        
        :param float: timeout in *seconds*
        :raises: SCPError
        
        .. note::
        
            On the SpiNNaker node, all timeouts are stored in an exponential
            representation that limits the number of valid timeout durations to
            a small set.  Timeouts are calculated (from the node's perspective)
            as follows::
            
                timeout = 10ms * 2^(tto - 1)
            
            Hence timeout values passed into this function will be decomposed
            into ``tto`` in the above equation.
        
        """
        
        # convert the timeout into the exponent as explained above
        tto = int (math.ceil (math.log ((timeout / 0.01), 2))) + 1
        if tto >= 16:
            raise ValueError ("specific timeout is too large.")
        
        # set the new transient timeout
        #   arg1 = 0 : command : 0 :    0
        #   arg2 = 0 :    0    : 0 : timeout
        #   arg3 = 0 :    0    : 0 :    0
        msg        = SCPMessage ()
        msg.cmd_rc = scamp.CMD_IPTAG
        msg.arg1   = scamp.IPTAG_TTO << 16
        msg.arg2   = tto
        msg.arg3   = 0
        self.send_scp_msg (msg)
    
    def get_iptag (self, index):
        """
        Retrieve an IP-tag from the target SpiNNaker machine.
        
        :param int index: index in the IP-tag table.
        :returns:         IP tag data in a :py:class:`IPTag`
        :raises:          SCPError
        
        """
        
        # build up the request as follows:
        #   arg1 = 0 : command : 0 :  tag
        #   arg2 = 0 :    0    : 0 : count
        #   arg3 = 0 :    0    : 0 :   0
        msg        = SCPMessage ()
        msg.cmd_rc = scamp.CMD_IPTAG
        msg.arg1   = scamp.IPTAG_GET << 16 | index
        msg.arg2   = 1
        msg.arg3   = 0
        resp_msg   = self.send_scp_msg (msg)
        
        # deconstruct the returned data
        if len (resp_msg.data) != 16:
            raise ValueError ("insufficient data received in response.")
        (ip, mac, port, timeout, flags) = struct.unpack ('<4s6s3H',
            resp_msg.data)
        
        # format the IP and MAC addresses correctly
        ip  = '.'.join (['%d'   % ord (c) for c in ip])
        mac = ':'.join (['%02X' % ord (c) for c in mac])
        
        # return the data as a struct
        return IPTag (ip=ip, mac=mac, port=port, timeout=timeout/100.0,
            flags=flags, index=index)
    
    def new_iptag (self, host, port, timeout=0):
        """
        Add a new IP-tag record at the next available slot.
        
        :param str host:    hostname or IP address of destination
        :param int port:    port to use on destination
        :param int timeout: specific timeout to use, or 0 for default
        :returns:           record index in the IP-tag table
        :raises:            SCPError
        
        """
        
        return self.set_iptag (None, host, port, timeout)

    def set_iptag (self, index, host, port, timeout=0):
        """
        Set an IP-tag record at the required index.
        
        :param int index:   index in the IP-tag table
        :param str host:    hostname or IP address of destination
        :param int port:    port to use on destination
        :param int timeout: specific timeout to use, or 0 for default
        :returns:           record index in the IP-tag table
        :raises:            SCPError
        
        """
        
        # clamp the port and timeout to their appropriate ranges
        timeout &= 0x000F
        port    &= 0xFFFF
        
        # ensure that the given hostname is always an IP
        if host.lower () in ("localhost", "127.0.0.1"):
            host = socket.gethostname ()
        ip = socket.gethostbyname (host)
        
        # decompose the IP address into the component numbers and store in an 
        # integer in REVERSE order so that it's correct after packing
        ip, segs = 0, ip.split ('.')
        if len (segs) != 4:
            raise ValueError ("IP address format is incorrect")
        for n, seg in enumerate (segs):
            ip |= (int (seg) << (8*n))
        
        # the first argument for this packet is a special case because the
        # index is allowed to be invalid.  if it is invalid then create a new
        # iptag record, otherwise update an existing tag
        msg = SCPMessage (cmd_rc=scamp.CMD_IPTAG)
        if index == None:
            msg.arg1 = scamp.IPTAG_NEW << 16
        else:
            msg.arg1 = scamp.IPTAG_SET << 16 | (index & 0xFF)
        
        # the rest of the arguments follow the order:
        #   arg2 = timeout : port
        #   arg3 = IP
        msg.arg2 = timeout << 16 | port
        msg.arg3 = ip
        
        # fire off the packet
        resp = self.send_scp_msg (msg)
        if len (resp.data) != 4:
            raise ValueError ("insufficient data received in response.")
        
        # the response contains the allocated tag index as an integer
        (ret_index, ) = struct.unpack ('<I', resp.data)
        return ret_index
    
    def clear_iptag (self, index):
        """
        Removes an IP-tag from the remote SpiNNaker.
        
        :param int index: index to remove from the table
        :raises:          SCPError
        
        """
        
        # build up the request as follows:
        #   arg1 = 0 : command : 0 : tag
        #   arg2 = 0 :    0    : 0 :  0
        #   arg3 = 0 :    0    : 0 :  0
        msg        = SCPMessage ()
        msg.cmd_rc = scamp.CMD_IPTAG
        msg.arg1   = (scamp.IPTAG_CLR << 16) | index
        
        # fire off the command
        self.send_scp_msg (msg)
    
    def get_all_iptags (self):
        """
        Retrieves all registered IP-tags from the target SpiNNaker machine.
        
        :returns: list of :py:class:`Struct`\ s containing IP-tag information
        :raises:  SCPError
        
        """
        
        iptags = []

        # get the total number of possible IP tag records
        fixed, trans, timeout = self.get_iptag_table_info ()
        
        # iterate over the possibilities
        for i in xrange (fixed + trans):
            iptag = self.get_iptag (i)
            
            # add valid records to the list
            if iptag.flags & scamp.IPTAG_VALID:
                iptags.append (iptag)
        
        # return whatever we found (possibly an empty list)
        return iptags
    
    def _check_size_alignment (self, type, size):
        """
        Utility function to ensure that ``size`` is of the correct alignment for
        the data-type in ``type``.
        
        :param int type: one of the ``TYPE_BYTE``, ``TYPE_HALF``, or
                         ``TYPE_WORD`` constants
        :param int size: size (in bytes) of the data
        :raises:         ValueError
        
        """
        
        if type == scamp.TYPE_BYTE:
            pass
        elif type == scamp.TYPE_HALF:
            # must be aligned to a short boundary
            if size % 2:
                raise ValueError ("data arranged as half-words but not aligned - size: %d" % size)
        elif type == scamp.TYPE_WORD:
            # must be aligned to a dword boundary
            if size % 4:
                raise ValueError ("data arranged as words but not aligned - size: %d" % size)
        else:
            # incorrect data type
            raise ValueError ("unknown data type: %d" % type)

    def gen_slice (self, seq, length):
        """
        Generator function to slice a container into smaller chunks.

        :param seq:        iterable container
        :param int length: length of each slice of ``seq``
        :returns:          appropriate slice of ``seq``

        Example::

            >>> for slice in gen_slice ("Hello!", 3):
            ...     print slice
            Hel
            lo!

        """

        start = 0
        end   = length

        # iterate over the container
        while True:
            # extract a new segment and update the slice bounds
            seg = seq[start:end]
            start += length
            end   += length

            # return segments until there aren't any left!
            if seg:
                yield seg
            else:
                raise StopIteration
      
    def write_mem (self, start_addr, type, data):
        """
        Uploads data to a target SpiNNaker node at a specific memory location.
        
        :param int start_addr: base address for the uploaded data
        :param int type:       one of ``TYPE_BYTE``, ``TYPE_HALF``, or
                               ``TYPE_WORD`` to indicate element type
        :param str data:       string of data to upload
        :raises:               SCPError
        
        """
        
        msg = SCPMessage (cmd_rc=scamp.CMD_WRITE, arg3=type)
        
        # confirm the data length is aligned to the appropriate boundary
        self._check_size_alignment (type, len (data))
        
        # upload the data in maximum-sized chunks
        addr = start_addr
        for chunk in self.gen_slice (data, scamp.SDP_DATA_SIZE):
            # build up the packet as follows:
            #   arg1 = start address
            #   arg2 = chunk length
            #   arg3 = element size
            msg.arg1    = addr
            msg.arg2    = len (chunk)
            msg.payload = chunk
            self.send_scp_msg (msg)
            
            # increment the address pointer
            addr += len (chunk)
    
    def write_mem_from_file (self, start_addr, type, filename,
            chunk_size=16384):
        """
        Uploads the contents of a file to the target SpiNNaker node at a
        specific memory location.
        
        :param int start_addr: base address for the uploaded data
        :param int type:       one of ``TYPE_BYTE``, ``TYPE_HALF``, or
                               ``TYPE_WORD`` to indicate element type
        :param str filename:   name of the source file to read from
        :param int chunk_size: number of bytes to read from the file in one go
        :raises:               IOError, SCPError
        
        """
        
        # open the file and determine its length
        print "Loading:",filename,"to", hex(start_addr)
        fd = file (filename, 'rb')
        fd.seek (0, os.SEEK_END)
        size = fd.tell ()
        fd.seek (0, os.SEEK_SET)
        
        # confirm the file is aligned correctly
        self._check_size_alignment (type, size)
        
        # read in the file in suitably sized chunks
        bytes_remaining = size
        addr            = start_addr
        while bytes_remaining > 0:
            # read a chunk and update the tracker variables
            chunk            = fd.read (chunk_size)
            bytes_remaining -= len (chunk)
            
            #print "Writing ",len(chunk)," bytes to ",hex(addr)," - ",bytes_remaining,"to go..."

            # write it into memory
            self.write_mem (addr, type, chunk)
            
            # update the address pointer
            addr += len (chunk)
        
        # close the file again
        fd.close ()
        
        return size
    
    def read_mem (self, start_addr, type, size):
        """
        Reads an amount of data from the target SpiNNaker node starting at
        address ``start_addr``.
        
        :param int start_addr: address to start reading from
        :param int type:       one of ``TYPE_BYTE``, ``TYPE_HALF``, or
                               ``TYPE_WORD`` to indicate element type
        :param int size:       number of bytes to read
        :returns:              string containing the data read
        :raises:               SCPError
        
        """
        
        msg = SCPMessage (cmd_rc=scamp.CMD_READ)
        
        # confirm the data size is aligned to the appropriate boundary
        self._check_size_alignment (type, size)
        
        # initialise tracker variables
        addr      = start_addr
        buf       = ''
        read_size = size
        
        # read all the data
        while (addr - start_addr) < size:
            # build up the packet as follows:
            #   arg1 = start address
            #   arg2 = chunk length
            #   arg3 = element size
            msg.arg1 = addr
            msg.arg2 = min (read_size, scamp.SDP_DATA_SIZE)
            msg.arg3 = type
            resp = self.send_scp_msg (msg)
            
            # add the data to the buffer and update the tracker variables
            buf       += resp.data
            addr      += len (resp.data)
            read_size -= len (resp.data)
        
        # return the (hopefully valid) data buffer
        return buf
    
    def read_mem_to_file (self, start_addr, type, size, filename,
            chunk_size=16384):
        """
        Reads the memory of a target SpiNNaker node, starting from a specific
        location, and then writes it into a file.
        
        :param int start_addr: address to start reading from
        :param int type:       one of ``TYPE_BYTE``, ``TYPE_HALF``, or
                               ``TYPE_WORD`` to indicate element type
        :param str filename:   name of the destination file to write into
        :param int chunk_size: number of bytes to write to the file in one go
        :raises:               IOError, SCPError
        
        """
        
        # check the type alignment
        self._check_size_alignment (type, size)
        
        # open a file for writing
        fd = open (filename, 'wb')
        
        # iterate over the memory and write it into a file
        addr       = start_addr
        bytes_left = size
        while bytes_left > 0:
            # read a chunk from the SpiNNaker and update the counter variables
            chunk       = self.read_mem (addr, type,
                min (chunk_size, bytes_left))
            bytes_left -= len (chunk)
            addr       += len (chunk)

            # write it to the file
            fd.write (chunk)
        
        # close the file
        fd.close ()
    
    def set_leds (self, led1=scamp.LED_NO_CHANGE, led2=scamp.LED_NO_CHANGE,
            led3=scamp.LED_NO_CHANGE, led4=scamp.LED_NO_CHANGE):
        """
        Changes the state of the LEDs of the target SpiNNaker node.
        
        :param int led1: action for LED 1
        :param int led2: action for LED 2
        :param int led3: action for LED 3
        :param int led4: action for LED 4
        :raises: SCPError
        
        Each ``ledN`` parameter may be given one of four values from the SC&MP
        definitions: ``LED_NO_CHANGE``, ``LED_INVERT``, ``LED_OFF``, or
        ``LED_ON``.
        
        """
        
        # LED control signals exist only in the lowest byte of arg1
        msg        = SCPMessage ()
        msg.cmd_rc = scamp.CMD_LED
        msg.arg1   = (led4 << 6) | (led3 << 4) | (led2 << 2) | led1
        self.send_scp_msg (msg)
    
    def reset_aplx(self, core_mask, app_id):
        """
        Resets a number of application cores, populating their ITCM from data located at 0x67800000 in SDRAM
        Executes an APLX image on the target SpiNNaker node.
        
        :param int core_mask: mask specifying which cores executable loaded into SDRAM at 0x67800000 should be loaded onto
        :param int app_id: arbitrary 8-bit identification number to give to this app
        :raises: SCPError
        
        """
        
         # simple packet:
        # **TODO** check validity of core mask (it's no longer than 24 bits) and app_id (it's no longer than 8 bits)
        #   arg1 = address of "table" (i.e. program start in SDRAM)
        #   arg2 = core mask (max 24 bits) masked with app id
        #   arg3 = unused
        msg        = SCPMessage ()
        msg.cmd_rc = scamp.CMD_AR
        msg.arg1   =  (app_id << 24) + core_mask
        
        self.send_scp_msg (msg)

    def exec_aplx (self, start_addr):
        """
        Executes an APLX image on the target SpiNNaker node.
        
        :param int start_addr: memory address of the APLX image
        :raises: SCPError
        
        """
        
        # simple packet:
        #   arg1 = address of "table" (i.e. program start in SDRAM)
        #   arg2 = unused parameter - must be 0
        #   arg3 = unused
        msg        = SCPMessage ()
        msg.cmd_rc = scamp.CMD_APLX
        msg.arg1   = start_addr
        self.send_scp_msg (msg)
    
    def exec_app_start (self, start_addr, cpu_mask):
        """
        Simultaneously executes APLX images on several processors in the target
        SpiNNaker node.
        
        :param int start_addr: memory address of the APLX image
        :param int cpu_mask: bit-mask of processors on which to execute the image
        :raises: SCPError
        
        ``cpu_mask`` is an integer *mask* where each bit corresponds to a
        processor on the target SpiNNaker node, i.e. bit N implies that the
        program should be executed on processor N.
        
        .. warning::
        
            The monitor processor **is** included in the ``cpu_mask`` which can
            lead to errors if the APLX image was not designed to run on the
            monitor core.
        
        """
        
        # simple packet:
        #   arg1 = address of program in memory
        #   arg2 = cpu mask - each bit corresponds to a core in the chip
        #   arg3 = unused
        msg        = SCPMessage ()
        msg.cmd_rc = scamp.CMD_AS
        msg.arg1   = start_addr
        msg.arg2   = cpu_mask
        self.send_scp_msg (msg)


# functions


# private classes
class VersionInfo (object):
    """
    SC&MP/SARK version information as returned by the SVER command.
    
    """
    
    def __init__ (self, msg):
        """
        Constructs a VersionInfo object.
        
        :param msg: :py:class:`SCPMessage` containing the information
        
        """
        
        data = msg.data
        
        # version info is actually in the argN space but as byte data and the
        # string descriptor follows
        verinfo = struct.unpack ('< 4B 2H I', data[:12])
        desc    = data[12:].strip ('\x00')
        
        # update the members
        (self.v_cpu, self.p_cpu, self.node_y, self.node_x, self.size,
            self.ver_num, self.time) = verinfo
        self.desc = desc
        
        # decode the version number
        self.ver_num /= 100.0

class IPTag (object):
    """
    IP tag data structure.
    
    """
    
    def __init__ (self, **kwargs):
        """
        Constructs an IPTag object.
        
        """
        
        members = ('ip', 'mac', 'port', 'timeout', 'flags', 'index')
        
        # copy the given value or default to None
        for member in members:
            self.__dict__[member] = kwargs.setdefault (member, None)
    
    def __str__ (self):
        """
        Pretty print method to help in interactive mode.
        
        Print format:
        
            index: ip:port [mac]; flags, timeout
        
        """
        
        return '{:d}: {:s}:{:d} [{:s}]; {:x}, {:.02f}'.format (self.index, 
            self.ip, self.port, self.mac, self.flags, self.timeout)


# private functions

