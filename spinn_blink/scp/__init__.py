#
# DESCRIPTION
#   Package script to bring all the SDP and SCP stuff into the package
#   namespace.
#
# AUTHORS
#   Kier J. Dugan - (kjd1v07@ecs.soton.ac.uk)
#
# DETAILS
#   Created on       : 21 July 2012
#   Revision         : $Revision: 198 $
#   Last modified on : $Date: 2012-07-18 17:51:12 +0100 (Wed, 18 Jul 2012) $
#   Last modified by : $Author: kjd1v07 $
#   $Id: __init__.py 198 2012-07-18 16:51:12Z kjd1v07 $
#
# COPYRIGHT
#   Copyright (c) 2012 The University of Southampton.  All Rights Reserved.
#   Electronics and Electrical Engingeering Group,
#   School of Electronics and Computer Science (ECS)
#

# imports
import scamp
from scamp import *
from legacy import build, parse
from boot import BootError, boot, reset
from sdp import SDPMessage, SDPConnection
from scp import SCPMessage, SCPConnection, SCPError

# constants
__all__  = [x for x in dir (scamp) if not x.startswith ('_')]
__all__ += ['build', 'parse', 'boot', 'readstruct', 'BootError', 'SDPMessage', 'SCPMessage',
    'SDPConnection', 'SCPConnection', 'SCPError', 'SDPDispatcher']
