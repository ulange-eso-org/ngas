#
#    ALMA - Atacama Large Millimiter Array
#    (c) European Southern Observatory, 2002
#    Copyright by ESO (in the framework of the ALMA collaboration),
#    All rights reserved
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston,
#    MA 02111-1307  USA
#

# *****************************************************************************
#
# "@(#) $Id: ngamsRegisterGenericPlugIn.py,v 1.2 2012/03/03 21:18:17 amanning Exp $"
#
# Who       When        What
# --------  ----------  -------------------------------------------------------
# jagonzal  199/01/2011  Created
#

"""
This Data Register Plug-In is used to generically handle the registration of files
already stored on an 'NGAS disk', which just need to be registered in the DB.

Note, that the plug-in is implemented for the usage at ESO. If used in other
contexts, a dedicated plug-in matching the individual context should be
implemented and NG/AMS configured to use it.
"""

import email.parser
import logging
import os

from ngamsLib import ngamsCore
from ngamsLib import ngamsPlugInApi
from ngamsLib.ngamsCore import genLog

PLUGIN_ID = __name__

logger = logging.getLogger(__name__)


def parse_multipart_primary_header(file_path):
    """
    Parses email MIME document file and extracts the primary header elements
    :param file_path: File path
    :return: email message object
    """
    filename = os.path.basename(file_path)
    try:
        # We read file using binary and decode to utf-8 later to ensure python 2/3 compatibility
        with open(file_path, 'rb') as fo:
            # Verify the file uses MIME format
            line = fo.readline().decode(encoding="utf-8")
            first_line = line.lower()
            if not first_line.startswith("message-id") and not first_line.startswith("mime-version"):
                raise Exception(genLog("NGAMS_ER_DAPI_BAD_FILE", [filename, PLUGIN_ID, "File is not MIME file format"]))
            # Read primary header block lines into the parser
            feedparser = email.parser.FeedParser()
            feedparser.feed(line)
            for line in fo:
                line = line.decode(encoding="utf-8")
                if line.startswith("\n"):
                    continue
                if line.startswith("--"):
                    break
                feedparser.feed(line)
            return feedparser.close()
    except Exception as e:
        raise Exception(genLog("NGAMS_ER_DAPI_BAD_FILE", [filename, PLUGIN_ID, "Failed to open file: " + str(e)]))


def get_multipart_file_content_type(file_path):
    """
    Unpack a MIME message and determine the content type (e.g. multipart/mixed or multipart/related)
    :param file_path: MIME message file path
    :return: MIME content type
    """
    mime_message = parse_multipart_primary_header(file_path)
    if mime_message.get_content_type() == 'multipart/mixed':
        return mime_message.get_content_type()
    elif mime_message.get_content_type() == 'multipart/related':
        return mime_message.get_content_type()
    else:
        return None


def ngamsRegisterAlmaPlugIn(server_object, request_object, param_dict):
    """
    Generic registration plug-in to handle registration of files
    :param server_object: Reference to NG/AMS Server Object (ngamsServer)
    :param request_object: NG/AMS request properties object (ngamsReqProps)
    :param param_dict: Parameter dictionary
    :return: Standard NG/AMS Data Archiving Plug-In Status as generated by  ngamsPlugInApi.genDapiSuccessStat()
    (ngamsDapiStatus)
    """
    logger.info("Register ALMA plug-in registering file with URI: %s", request_object.getFileUri())
    disk_info = request_object.getTargDiskInfo()
    mime_type = request_object.getMimeType()
    stage_file = request_object.getStagingFilename()
    file_id = os.path.basename(request_object.getFileUri())

    if mime_type == ngamsCore.NGAMS_UNKNOWN_MT:
        content_type = get_multipart_file_content_type(stage_file)
        if content_type is None:
            error_message = genLog("NGAMS_ER_UNKNOWN_MIME_TYPE1", [file_id])
            raise Exception(error_message)
        else:
            mime_type = content_type

    file_size = ngamsPlugInApi.getFileSize(stage_file)
    compression = ""
    uncompressed_size = file_size

    file_version, relative_path, relative_filename, complete_filename, file_exists = \
        ngamsPlugInApi.genFileInfoReg(server_object.getDb(), server_object.getCfg(), request_object, disk_info,
                                      stage_file, file_id)

    logger.info("Register ALMA plug-in finished processing file with URI %s: file_id=%s, file_version=%s, format=%s, file_size=%s",
                request_object.getFileUri(), file_id, file_version, mime_type, file_size)

    return ngamsPlugInApi.genRegPiSuccessStat(disk_info.getDiskId(), relative_filename, file_id, file_version,
                                              mime_type, file_size, uncompressed_size, compression, relative_path,
                                              disk_info.getSlotId(), file_exists, complete_filename)
