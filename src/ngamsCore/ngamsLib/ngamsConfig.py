#
#    ICRAR - International Centre for Radio Astronomy Research
#    (c) UWA - The University of Western Australia, 2012
#    Copyright by UWA (in the framework of the ICRAR)
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
#******************************************************************************
#
# "@(#) $Id: ngamsConfig.py,v 1.26 2009/11/26 14:55:22 awicenec Exp $"
#
# Who       When        What
# --------  ----------  -------------------------------------------------------
# jknudstr  07/05/2001  Created
#

"""
The ngamsConfig class is used to handle the NG/AMS Configuration.
"""

import base64
import collections
import logging
import os
import types

from   ngamsCore import genLog, TRACE, checkCreatePath, NGAMS_UNKNOWN_MT, isoTime2Secs, getNgamsVersionRaw, NGAMS_PROC_DIR, NGAMS_BACK_LOG_DIR
import ngamsConfigBase, ngamsSubscriber
import ngamsStorageSet, ngamsStream, ngamsMirroringSource


logger = logging.getLogger(__name__)

def boolean_value(val):
    if val.lower() == 'true':
        return True
    elif val.lower() == 'false':
        return False
    return None

def int_value(val):
    try:
        return int(val)
    except ValueError:
        return None

def float_value(val):
    try:
        return float(val)
    except ValueError:
        return None

def getInt(property,
           val,
           retValOnFailure = -1):
    """
    Get an integer value from what is extracted from the XML document
    and make an overall validity check of the value.

    property:         Property being checked, e.g. <element>.<attrbute>
                      (string).

    val:              Value as extracted from the XML document (string|?).

    retValOnFailure:  Value to return in case the integer value could not
                      be converted (all types).

    Returns:          Integer value (integer).
    """
    try:
        valInt = int(str(val))
        return valInt
    except Exception, e:
        return retValOnFailure


def checkIfSetStr(property,
                  value,
                  checkRep = None):
    """
    Check if the value given is of type string, and is different from "".

    property:  Name of property being tested (string).

    value:     Value of property (string).

    checkRep:  List, which will contain the errors encountered (list).

    Returns:   1 is returned if string checked is OK. 0 is returned
               if the string was not properly formatted (integer/0|1).
    """
    logging.debug("Checking if property: %s is properly set ...", property)
    if ((not isinstance(value, types.StringType))):
        errMsg = "Must define a proper string value for property: " + property
        errMsg = genLog("NGAMS_ER_CONF_PROP", [errMsg])
        logger.error(errMsg)
        if (checkRep != None):
            checkRep.append(errMsg)
            return 0
        else:
            raise Exception, errMsg
    elif value == "":
        logger.warning("Value of property %s is an empty string", property)
    else:
        return 1


def checkIfSetInt(property,
                  value,
                  checkRep = None):
    """
    Check if the value given is of type integer, and is different from -1.

    property:  Name of property being tested (string).

    value:     Value of property (integer).

    checkRep:  List, which will contain the errors encountered (list).

    Returns:   1 is returned if value checked is OK. 0 is returned
               if the value was not properly formatted (integer/0|1).
    """
    logger.debug("Checking if property: %s is properly set ...", property)
    value = int(value)
    if ((not isinstance(value, types.IntType)) or (value == -1)):
        errMsg = "Must define a proper integer value for property: " + property
        errMsg = genLog("NGAMS_ER_CONF_PROP", [errMsg])
        logger.error(errMsg)
        if (checkRep != None):
            checkRep.append(errMsg)
            return 0
        else:
            raise Exception, errMsg
    else:
        return 1


def checkIfZeroOrOne(property,
                     value,
                     checkRep = None):
    """
    Check if value for a property is 0 or 1. If not throw exception.

    property:   Name of property being tested (string).

    value:      Value of property (integer).

    checkRep:   List, which will contain the errors encountered (list).

    Returns:    1 is returned if value checked is OK. 0 is returned
                if the value was not properly formatted (integer/0|1).
    """
    logger.debug("Checking if property: %s is properly set ...", property)
    if ((not isinstance(value, types.IntType)) or
        ((value != 0) and (value != 1))):
        errMsg = "Value must be 0 or 1 (integer) for property: " + property
        errMsg = genLog("NGAMS_ER_CONF_PROP", [errMsg])
        logger.error(errMsg)
        if (checkRep != None):
            checkRep.append(errMsg)
            return 0
        else:
            raise Exception, errMsg
    else:
        return 1


def checkDuplicateValue(checkDic,
                        property,
                        value,
                        checkRep = None):
    """
    Check if the given propery was already registered as key in the
    dictionary referenced.

    checkDic:    Dictionary containing the property names as keys (dictionary).

    property:    Name of property being tested (string).

    value:       Value of property (*).

    checkRep:    List, which will contain the errors encountered (list).

    Returns:     Void.
    """
    if (checkDic.has_key(value)):
        errMsg = "Duplicate value for property: " + property + ". Value: " +\
                 str(value)
        errMsg = genLog("NGAMS_ER_CONF_PROP", [errMsg])
        logger.error(errMsg)
        if (checkRep != None):
            checkRep.append(errMsg)
        else:
            raise Exception, errMsg
    else:
        checkDic[value] = 1

class ngamsConfigException(Exception): pass

# A simple plug-in definition contains a name and some parameters
plugin_def = collections.namedtuple('plugin_def', 'name pars')
dppi_plugin_def = collections.namedtuple('dppi_plugin_def', 'name pars mime_types')


class ngamsConfig:
    """
    Class to handle the information in the NG/AMS Configuration.
    """

    def __init__(self,
                 filename = "",
                 dbObj = None):
        """
        Constructor method. If a valid filename is specified this
        will be loaded.

        filename:    Filename of NG/AMS Configuration file (string).

        dbConObj:    DB connection object (ngamsDb).
        """
        self.__cfgMgr = ngamsConfigBase.ngamsConfigBase(None, dbObj)
        self.clear()
        if (self.getCfg()): self.load(filename)


    def clear(self):
        """
        Clear the object.

        Returns:   Reference to object itself.
        """
        # Mime-type mappings (attributes in the MimeTypes Element).
        self.__mimeType2ExtDic         = {}
        self.__ext2MimeTypeDic         = {}

        # List with Storage Sets.
        self.__storageSetList          = []

        # List of Stream Objects.
        self.__streamList              = []

        # List of command plug-ins
        self.cmd_plugins               = {}

        # Data Processing Plug-Ins, indexed by name
        self.dppi_plugins              = {}

        # Archiving event Plug-Ins
        self.archive_evt_plugins       = {}

        # Logfile handler Plug-Ins
        self.logfile_handler_plugins   = []

        # Janitor process Plug-Ins
        self.__janitorPlugIns          = []

        # Logfile handler Plug-Ins
        self.logfile_handler_plugins   = []

        # Register Plug-Ins, indexed by mime type
        self.register_plugins          = {}

        # List with recepients of Email Notification Messages.
        self.__alertNotif              = []
        self.__errorNotif              = []
        self.__diskSpaceNotif          = []
        self.__diskChangeNotif         = []
        self.__noDiskSpaceNotif        = []
        self.__dataCheckNotif          = []

        self.__checkRep                = []

        # Dictionary with Subscribers.
        self.__subscriptionsDic        = {}

        # User IDs for HTTP authentication.
        self.__authUserDic             = {}

        # key user name, value: allowed user commands separated by comma
        self.__authUserCommandsDic     = {}

        # Mirroring sources.
        self.__mirSrcObjList           = []
        self.__mirSrcObjDic            = {}

        return self


    def getCfg(self):
        """
        Get the name of the configuration file loaded into the object.

        Returns:   Name of configuration file (string).
        """
        return self.__cfgMgr.getXmlDoc()


    def setDbObj(self,
                 dbObj):
        """
        Set the DB connection object of this instance.

        dbObj:    DB connection object (ngamsDb).

        Returns:  Reference to object itself.
        """
        self.__cfgMgr.setDbObj(dbObj)
        return self


    def writeToDb(self,
                  dbObj = None):
        """
        Write the configuration loaded into the DB.

        dbObj:    DB connection object (ngamsDb).

        Returns:  Reference to object itself.
        """
        if (dbObj): self.setDbObj(dbObj)
        self.__cfgMgr.writeToDb()
        return self


    def loadFromDb(self,
                   name,
                   dbObj = None):
        """
        Load a configuration from the DB via the given ID.

        name:       Name of the configuration in the DB (string).

        dbObj:      DB connection object (ngamsDb).

        Returns:    Reference to object itself.
        """
        if (dbObj): self.setDbObj(dbObj)
        self.__cfgMgr.loadFromDb(name)
        self._unpackCfg()
        return self


    def _getXmlDic(self):
        """
        Return the internal dictionary representing the XML document.

        Returns:   XML dictionary (dictionary).
        """
        return self.__cfgMgr.getXmlDic()


    def dumpXmlDic(self):
        """
        Dump the contents of the XML Dictionary in a buffer in the format:

          <Key> = <Value>
          <Key> = <Value>
          ...

        Returns:    Reference to string buffer with the XML Dictionary dump
                    (string).
        """
        return self.__cfgMgr.dumpXmlDic()


    def load(self,
             filename,
             check = 0):
        """
        Load an NG/AMS Configuration File into the object.

        filename:  Name of configuration file (string).

        check:     If set to 1 the semantics is checked after loading
                   (integer/0|1).

        Returns:   Reference to object itself.
        """
        T = TRACE()

        self.clear()
        try:
            self.__cfgMgr.load(filename)
        except Exception, e:
            errMsg = genLog("NGAMS_ER_LOAD_CFG", [filename, str(e)])
            raise Exception, errMsg
        self._unpackCfg()
        if (check): self._check()

        return self


    def _unpackCfg(self):
        """
        Unpack specific elements of the configuration.

        Returns:     Reference to object itself.
        """
        T = TRACE()

        self.clear()

        # Create log file directory if defined.
        if (self.getLocalLogFile()):
            checkCreatePath(os.path.dirname(self.getLocalLogFile()))

        # Get command plug-ins
        commands_obj = self.__cfgMgr.getXmlObj('Commands[1]')
        if commands_obj:
            logger.debug('Unpacking Commands element')
            cmdattr_fmt = 'Commands[1].Command[%d].%s'
            for idx in range(1, len(commands_obj.getSubElList()) + 1):
                name = self.getVal(cmdattr_fmt % (idx, 'Name'))
                module = self.getVal(cmdattr_fmt % (idx, 'Module'))
                self.cmd_plugins[name] = module

        # Get Mime-types.
        mimeTypesObj = self.__cfgMgr.getXmlObj("MimeTypes[1]")
        if (mimeTypesObj):
            logger.debug("Unpacking MimeTypes Element ...")
            attrFormat = "MimeTypes[1].MimeTypeMap[%d].%s"
            for idx in range(1, (len(mimeTypesObj.getSubElList()) + 1)):
                ext  = self.getVal(attrFormat % (idx, "Extension"))
                mimeType = self.getVal(attrFormat % (idx, "MimeType"))
                self.addMimeTypeMap(mimeType, ext)

        # Get Storage Sets.
        stoSetsObj = self.__cfgMgr.getXmlObj("StorageSets[1]")
        if (stoSetsObj):
            logger.debug("Unpacking StorageSets Element ...")
            attrFormat = "StorageSets[1].StorageSet[%d]"
            for idx in range(1, (len(stoSetsObj.getSubElList()) + 1)):
                nm = attrFormat % idx + ".%s"
                setObj = ngamsStorageSet.\
                         ngamsStorageSet(self.getVal(nm % "StorageSetId"),
                                         self.getVal(nm % "DiskLabel"),
                                         self.getVal(nm % "MainDiskSlotId"),
                                         self.getVal(nm % "RepDiskSlotId"),
                                         self.getVal(nm % "Mutex"),
                                         self.getVal(nm % "Synchronize"))
                self.addStorageSetObj(setObj)

        # Handle Streams.
        streamsObj = self.__cfgMgr.getXmlObj("Streams[1]")
        if (streamsObj):
            logger.debug("Unpacking Streams Element ...")
            attrFormat1 = "Streams[1].Stream[%d]"
            attrFormat2 = attrFormat1 + ".StorageSetRef[%d].StorageSetId"
            attrFormat3 = attrFormat1 + ".ArchivingUnit[%d].HostId"

            for idx1 in range(1, (len(streamsObj.getSubElList()) + 1)):
                nm = attrFormat1 % idx1 + ".%s"
                tmpStrObj = ngamsStream.\
                            ngamsStream(self.getVal(nm % "MimeType"),
                                        self.getVal(nm % "PlugIn"),
                                        self.getVal(nm % "PlugInPars"))

                # Get Storage Set/Archiving Unit Refrences.
                streamObj = self.__cfgMgr.getXmlObj(attrFormat1 % idx1)
                stoSetIdx = archUnitIdx = 1
                for subEl in streamObj.getSubElList():
                    for attrEl in subEl.getAttrList():
                        if (attrEl.getName() == "StorageSetId"):
                            val = self.getVal(attrFormat2 % (idx1, stoSetIdx))
                            tmpStrObj.addStorageSetId(val)
                            stoSetIdx += 1
                        else:
                            val = self.getVal(attrFormat3 % (idx1,archUnitIdx))
                            tmpStrObj.addHostId(val)
                            archUnitIdx += 1

                self.addStreamObj(tmpStrObj)

        # Get information about DPPIs.
        procObj = self.__cfgMgr.getXmlObj("Processing[1]")
        if (procObj):
            logger.debug("Unpacking Processing Element ...")
            prefix = "Processing[1].PlugIn[%d]"
            mime_type = prefix + ".MimeType[%d].Name"
            for i in range(1, (len(procObj.getSubElList()) + 1)):
                mime_types = []
                plugInElObj = self.__cfgMgr.getXmlObj(prefix % i)
                for j in range(1,(len(plugInElObj.getSubElList()) + 1)):
                    mime_types.append(self.getVal(mime_type % (i, j)))
                attr = prefix + ".%s"
                plugin = dppi_plugin_def(self.getVal(attr % (i, "Name")),
                                         self.getVal(attr % (i, "PlugInPars")),
                                         mime_types)
                self.dppi_plugins[plugin.name] = plugin

        # Get info about Register Plug-Ins.
        regObj = self.__cfgMgr.getXmlObj("Register[1]")
        if (regObj):
            logger.debug("Unpacking Register Element ...")
            prefix = "Register[1].PlugIn[%d]"
            mime_type = prefix + ".MimeType[%d].Name"
            for i in range(1, (len(regObj.getSubElList()) + 1)):

                plugInElObj = self.__cfgMgr.getXmlObj(prefix % i)
                attr = prefix + ".%s"
                plugin = plugin_def(self.getVal(attr % (i, "Name")),
                                    self.getVal(attr % (i, "PlugInPars")))
                for j in range(1,(len(plugInElObj.getSubElList()) + 1)):
                    mtype = self.getVal(mime_type % (i, j))
                    self.register_plugins[mtype] = plugin

                    # TODO: Here I'd like to check that the same mimetype is not
                    # associated to two different plug-ins, but there is a test
                    # (i.e., ngamsConfigHandlingTest#test_ServerLoad_3 that
                    # relies on this not failing
                    #if mtype in self.register_plugins:
                    #    msg = ("MIME type %s has more than one associated register"
                    #           " plug-in: %s and %s")
                    #    msg = msg % (mtype, self.register_plugins[mtype].name, plugin.name)
                    #    raise ngamsConfigException(msg)


        # Get info about Janitor Plug-Ins.
        janitorObj = self.__cfgMgr.getXmlObj("JanitorThread[1]")
        if janitorObj:
            logger.debug("Unpacking JanitorThread Element ...")
            name_path = "JanitorThread[1].PlugIn[%d].Name"
            for idx1 in range(1, (len(janitorObj.getSubElList()) + 1)):
                name = self.getVal(name_path % (idx1,))
                self.__janitorPlugIns.append(name)

        # Get info about Archive event Plug-Ins
        archive_handling = self.__cfgMgr.getXmlObj('ArchiveHandling[1]')
        if archive_handling:
            name_pattern = 'ArchiveHandling[1].EventHandlerPlugIn[%d].Name'
            pars_pattern = 'ArchiveHandling[1].EventHandlerPlugIn[%d].PlugInPars'
            for idx1 in range(1, (len(archive_handling.getSubElList()) + 1)):
                name = self.getVal(name_pattern % idx1)
                pars = self.getVal(pars_pattern % idx1)

                # Make sure the plug-in name is valid
                parts = name.split('.')
                module, clazz = '.'.join(parts[:-1]), parts[-1]
                if not module or not clazz:
                    raise ValueError("module or classname missing in EventHandlerPlugIn.Name definition")
                self.archive_evt_plugins[(module, clazz)] = pars

        # Get info about logfile handler plug-ins
        logObj = self.__cfgMgr.getXmlObj('Log[1]')
        if logObj:
            logger.debug("Unpacking LogfileHandlerPlugIn elements")
            attr = "Log[1].LogfileHandlerPlugIn[%d].%s"
            for i in range(1, len(logObj.getSubElList()) + 1):
                lh_plugin = plugin_def(self.getVal(attr % (i, "Name")),
                                       self.getVal(attr % (i, "PlugInPars")))
                self.logfile_handler_plugins.append(lh_plugin)

        # Process the information about subscribers to Notification Emails.
        attrList = [["AlertNotification",       self.__alertNotif],
                    ["ErrorNotification",       self.__errorNotif],
                    ["DiskSpaceNotification",   self.__diskSpaceNotif],
                    ["DiskChangeNotification",  self.__diskChangeNotif],
                    ["NoDiskSpaceNotification", self.__noDiskSpaceNotif],
                    ["DataCheckNotification",   self.__dataCheckNotif]]
        attrFormat = "Notification[1].%s[1].EmailRecipient[%s].Address"
        logger.debug("Unpacking Email Notification Recipients ...")
        for attr in attrList:
            idx = 1
            while (1):
                address = self.getVal(attrFormat % (attr[0], idx))
                if (address):
                    attr[1].append(address)
                    idx += 1
                else:
                    break

        # Get info about the subscribers.
        subscrDefObj = self.__cfgMgr.getXmlObj("SubscriptionDef[1]")
        if (subscrDefObj):
            logger.debug("Unpacking SubscriptionDef Element ...")
            fm = "SubscriptionDef[1].Subscription[%d].%s"
            for idx in range(1, (len(subscrDefObj.getSubElList()) + 1)):
                subscr_id = self.getVal(fm % (idx, "SubscriberId"))
                if subscr_id == None:
                    subscr_id = ""
                tmpSubscrObj = ngamsSubscriber.ngamsSubscriber(\
                    self.getVal(fm % (idx, "HostId")),
                    self.getVal(fm % (idx, "PortNo")),
                    self.getVal(fm % (idx, "Priority")),
                    self.getVal(fm % (idx, "SubscriberUrl")),
                    "",
                    self.getVal(fm % (idx, "FilterPlugIn")),
                    self.getVal(fm % (idx, "FilterPlugInPars")),
                    subscrId=subscr_id)
                self.getSubscriptionsDic()[tmpSubscrObj.getId()] = tmpSubscrObj

        # Process the Authentication Users.
        authObj = self.__cfgMgr.getXmlObj("Authorization[1]")
        if (authObj):
            logger.debug("Unpacking Authorization Element ...")
            fm = "Authorization[1].User[%d].%s"
            for idx in range(1, (len(authObj.getSubElList()) + 1)):
                userName = self.getVal(fm % (idx, "Name"))
                self.addAuthUser(userName,
                                 self.getVal(fm % (idx, "Password")))
                self.addAuthUserCommands(userName,
                                 self.getVal(fm % (idx, "Commands")))

        # Unpack information in Mirroring Element.
        srcArchIdDic = {}
        mirElObj = self.__cfgMgr.getXmlObj("Mirroring[1]")
        if (mirElObj):
            logger.debug("Unpacking Mirroring Element ...")
            attrFormat = "Mirroring[1].MirroringSource[%d]"
            for idx in range(1, (len(mirElObj.getSubElList()) + 1)):
                nm = attrFormat % idx + ".%s"
                mirSrcObj =\
                          ngamsMirroringSource.\
                          ngamsMirroringSource().\
                          setId(self.getVal(nm % "Id")).\
                          setServerList(self.getVal(nm % "ServerList")).\
                          setPeriod(self.getVal(nm % "Period")).\
                          setCompleteSync(self.getVal(nm % "CompleteSync")).\
                          setSyncType(self.getVal(nm % "SyncType")).\
                          setTargetNodes(self.getVal(nm % "TargetNodes")).\
                          setFilterPlugIn(self.getVal(nm % "FilterPlugIn")).\
                          setFilterPlugInPars(self.getVal(nm %\
                                                          "FilterPlugInPars"))
                if (srcArchIdDic.has_key(mirSrcObj.getId())):
                    msg = "Error parsing configuration file. Mirroring " +\
                          "Source Archive ID: %s specified multiple times"
                    raise Exception, msg % mirSrcObj.getId()
                self.addMirroringSrcObj(mirSrcObj)

        return self


    def getVal(self,
               parName):
        """
        Return the value of a parameter.

        parName:   Name of the parameter in the 'Simplified XPath Syntax',
                   e.g.:

                     NgamsCfg.Server[1].ArchiveName              (string).

        Returns:   Value of parameter or None (<Value>|None).
        """
        return self.__cfgMgr.getVal(parName)


    def storeVal(self,
                 parName,
                 value,
                 dbCfgGroupId = None):
        """
        Set the value of the given parameter.

        parName:      Name of parameter e.g.:

                        NgamsCfg.Server[1].RootDirectory     (string).

        value:        Value of the parameter (string).

        dbCfgGroupId: DB configuration group ID (string|None).

        Returns:      Reference to object itself.
        """
        self.__cfgMgr.storeVal(parName, value, dbCfgGroupId)
        return self


    def getArchiveName(self):
        """
        Get name of the archive.

        Returns:    Name of archive (string).
        """
        return self.getVal("Server[1].ArchiveName")


    def getSimulation(self):
        """
        Get NGAS Simulation Flag.

        Returns:  NGAS Simulation Flag (integer).
        """
        par = "Server[1].Simulation"
        return getInt(par, self.getVal(par))


    def getRootDirectory(self):
        """
        Get NGAS Root Directory.

        NOTE: THE NGAMS_PREFIX environment variable overrides the one in the
        Config-file.

        Returns:  NGAS Root Directory (string).
        """
        rootDir = self.getVal("NgamsCfg.Server[1].RootDirectory")
        if not rootDir:
            raise Exception, "Server[1].RootDirectory not properly defined"
        return rootDir


    def getVolumeDirectory(self):
        """
        Return value of the Volume Directory attribute in the Server Element.

        Returns:   Value of VolumeDirectory (string).
        """
        try:
            volDir = self.getVal("Server[1].VolumeDirectory")
        except:
            return ""
        if (not volDir): volDir = ""
        if volDir != "" and volDir[0] != '/':
            volDir = self.getRootDirectory() + '/' + volDir
        return volDir


    def getProcessingDirectory(self):
        """
        Get NG/AMS Processing Directory.

        Returns:   Processing directory (string).
        """
        procDir = self.getVal("Processing[1].ProcessingDirectory")
        if procDir == "." or procDir[0] != '/':
            if procDir == ".": procDir = ""
            procDir = self.getRootDirectory() + '/' + procDir
        return procDir


    def getPortNo(self):
        """
        Get socket port number.

        Returns:   Reference to object itself.
        """
        par = "Server[1].PortNo"
        return getInt(par, self.getVal(par))


    def getIpAddress(self):
        """
        Get socket port number.

        Returns:   Reference to object itself.
        """
        par = "Server[1].IpAddress"
        return self.getVal(par)

    def getTimeOut(self):
        """
        Gets the timeout that applies to HTTP requests.
        """
        par = "Server[1].TimeOut"
        return getInt(par, self.getVal(par), None)

    def getSwVersion(self):
        """
        Get the SW Version.

        Returns:   Reference to object itself.
        """
        swVersion = self.getVal("Server[1].SwVersion")
        if ((not swVersion) or (swVersion == "None")):
            return ""
        else:
            return swVersion

    def getPluginsPath(self):
        """
        Get the directory where plug-ins are placed.
        """
        return self.getVal("Server[1].PluginsPath")


    def getOnlinePlugIn(self):
        """
        Get name of Online Plug-In.

        Returns:  Name of Online Plug-In (string).
        """
        return self.getVal("SystemPlugIns[1].OnlinePlugIn")


    def getOnlinePlugInPars(self):
        """
        Get input parameters for Online Plug-In.

        Returns:  Input parameters for Online Plug-In (string).
        """
        return self.getVal("SystemPlugIns[1].OnlinePlugInPars")


    def getOfflinePlugIn(self):
        """
        Get name of Offline Plug-In.

        Returns:  Name of Offline Plug-In (string).
        """
        return self.getVal("SystemPlugIns[1].OfflinePlugIn")


    def getOfflinePlugInPars(self):
        """
        Get input parameters for Offline Plug-In.

        Returns:  Input parameters for Offline Plug-In (string).
        """
        return self.getVal("SystemPlugIns[1].OfflinePlugInPars")


    def getLabelPrinterPlugIn(self):
        """
        Get name of Label Printer Plug-In.

        Returns:  Name of Printer Plug-In (string).
        """
        return self.getVal("SystemPlugIns[1].LabelPrinterPlugIn")


    def getLabelPrinterPlugInPars(self):
        """
        Get input parameters for Label Printer Plug-In.

        Returns:  Input parameters for Label Printer Plug-In (string).
        """
        return self.getVal("SystemPlugIns[1].LabelPrinterPlugInPars")


    def getDiskSyncPlugIn(self):
        """
        Get name of the Disk Sync Plug-In.

        Returns:  Name of Disk Sync Plug-In (string).
        """
        return self.getVal("SystemPlugIns[1].DiskSyncPlugIn")


    def getDiskSyncPlugInPars(self):
        """
        Get input parameters for Disk Sync Plug-In.

        Returns:  Input parameters for Disk Sync Plug-In (string).
        """
        return self.getVal("SystemPlugIns[1].DiskSyncPlugInPars")


    def getReplication(self):
        """
        Return File Replication on/off flag.

        Returns:    File Replication on/off flag (integer).
        """
        par = "ArchiveHandling[1].Replication"
        return getInt(par, self.getVal(par))


    def getCRCVariant(self):
        """
        Defines the CRC Variant to use.

        Returns: -1: Don't perform any CRC calculation at all
                 0: crc32 (using python's binascii implementation)
                 1: crc32c (using Intel's SSE 4.2 implementation via our
                    custom crc32c module)
        """
        par = "ArchiveHandling[1].CRCVariant"
        return getInt(par, self.getVal(par), 0)


    def getBlockSize(self):
        """
        Get HTTP data read/write block size.

        Returns:   HTTP data read/write block size (integer).
        """
        par = "Server[1].BlockSize"
        return getInt(par, self.getVal(par))

    def getArchiveRcvBufSize(self):
        """
        Get TCP receive buffer size, which
        sets the upper limit of the TCP window size
        """
        par = "Server[1].ArchiveRcvBufSize"
        return getInt(par, self.getVal(par), retValOnFailure = None)

    def getArchiveSndBufSize(self):
        """
        Get TCP send buffer size, which
        sets the upper limit of the TCP window size
        """
        par = "Server[1].ArchiveSndBufSize"
        return getInt(par, self.getVal(par), retValOnFailure = None)

    def getMaxSimReqs(self):
        """
        Get the maximum number of simultaneous requests.

        Returns:   Maximum number of simultaneous requests (integer).
        """
        par = "Server[1].MaxSimReqs"
        return getInt(par, self.getVal(par))


    def getMinSpaceSysDirMb(self):
        """
        Get the minimum amount of free disk space required on the NG/AMS System
        Directories.

        Returns:    Minimum space (integer).
        """
        par = "JanitorThread[1].MinSpaceSysDirMb"
        return getInt(par, self.getVal(par))


    def getAllowArchiveReq(self):
        """
        Get the Allow Archive Request Flag.

        Returns:   Allow Archive Request Flag (integer).
        """
        par = "Permissions[1].AllowArchiveReq"
        return getInt(par, self.getVal(par))


    def getAllowRetrieveReq(self):
        """
        Get the Allow Retrieve Request Flag.

        Returns:   Allow Retrieve Request Flag (integer).
        """
        par = "Permissions[1].AllowRetrieveReq"
        return getInt(par, self.getVal(par))


    def getAllowProcessingReq(self):
        """
        Get the Allow Processing Request Flag.

        Returns:   Allow Processing Request Flag (integer).
        """
        par = "Permissions[1].AllowProcessingReq"
        return getInt(par, self.getVal(par))


    def getAllowRemoveReq(self):
        """
        Get the Allow Remove Request Flag.

        Returns:   Allow Remove Request Flag (integer).
        """
        par = "Permissions[1].AllowRemoveReq"
        return getInt(par, self.getVal(par))


    def getProxyMode(self):
        """
        Get Proxy Mode Flag.

        Returns:    Proxy Mode Flag (integer).
        """
        par = "Server[1].ProxyMode"
        return getInt(par, self.getVal(par))

    def getProxyCRC(self):
        """
        If the proxy archive server
        check CRC as well

        By default, 0 (do not check CRC)
        """
        par = "Server[1].ProxyCRC"
        return getInt(par, self.getVal(par), retValOnFailure = 0)


    def getArchiveUnits(self):
        """
        Get Archive Units.

        Returns:    Archive Units (string).
        """
        return self.getVal("ArchiveHandling[1].ArchiveUnits")


    def getJanitorSuspensionTime(self):
        """
        Get Janitor Service Suspension Time.

        Returns:   Janitor Service Suspension Time (string).
        """
        return self.getVal("JanitorThread[1].SuspensionTime")

    def getJanitorPlugins(self):
        """
        Get the list of Janitor Plug-in names.

        Returns:   Janitor Service Suspension Time (string).
        """
        return self.__janitorPlugIns

    def getBackLogBuffering(self):
        """
        Get the enable/disable Back Log Buffering Flag.

        Returns:    Back Log Buffering on/off (0/1) (integer).
        """
        par = "ArchiveHandling[1].BackLogBuffering"
        return getInt(par, self.getVal(par))


    def getBackLogBufferDirectory(self):
        """
        Get the Back Log Buffer Directory.

        Returns:   Back Log Buffer Directory (string).
        """
        bbufDir = self.getVal("ArchiveHandling[1].BackLogBufferDirectory")
        if bbufDir == "." or bbufDir[0] != '/':
            if bbufDir == ".": bbufDir = ""
            bbufDir = self.getRootDirectory() + '/' + bbufDir
        return bbufDir


    def getDbSnapshot(self):
        """
        Return the DB Snapshot Feature on/off.

        Returns:   DB Snapshot Feature state (integer/0|1).
        """
        par = "Db[1].Snapshot"
        return getInt(par, self.getVal(par))


    def getDbInterface(self):
        """
        Get the name of the NG/AMS DB Interface Plug-In in use.

        Returns:   DB Interface Plug-In (string).
        """
        return self.getVal("Db[1].Interface")


    def getDbMaxPoolCons(self):
        """
        Max number of DB Pool Connections.

        NOTICE: 7 connections was chosen as a default to allow for all the NGAS
        background services to have a long running db connection while allowing
        user requests to be serviced. Anything less than 7 with all the services
        enabled might cause user requests to block waiting for a db connection
        to be placed back in the pool from a long running service. 

        Returns: Max number of DB Pool Connections.
        """
        par = "Db[1].MaxPoolConnections"
        return getInt(par, self.getVal(par), 7)


    def getDbParameters(self):
        """
        Return DB connection parameters.

        Returns:  DB connection parameters (string).
        """
        dbEl = self.__cfgMgr.getXmlObj("Db[1]")
        params = {}
        for attr in dbEl.getAttrList():
            name = attr.getName()
            val = attr.getValue()
            if name in ('Id', 'Interface', 'Snapshot', 'UseFileIgnore', 'MaxPoolConnections'):
                continue

            # Simple casting before saving
            bVal = boolean_value(val)
            iVal = int_value(val)
            fVal = float_value(val)
            if bVal is not None:
                val = bVal
            elif iVal is not None:
                val = iVal
            elif fVal is not None:
                val = fVal
            params[name] = val

        return params

    def getDbUseFileIgnore(self):
        """
        Indicates whether to use "file_ignore" as the column name on the
        "ngas_files" table as opposed to "ignore". For historical reasons
        the same column has been referenced using two different names.
        """
        val = self.getVal("Db[1].UseFileIgnore")
        if val is not None:
            val = boolean_value(val)
        if val is None:
            return True
        return val


    def addMimeTypeMap(self,
                       mimeType,
                       extension):
        """
        Add a mime-type map to the object.

        mimeType:     Mime-type (string).

        extension:    Extension corresponding to mime-type (string).

        Returns:      Reference to object itself.
        """
        self.__mimeType2ExtDic[mimeType] = str(extension)
        self.__ext2MimeTypeDic[extension] = str(mimeType)
        return self


    def getExtFromMimeType(self,
                           mimeType):
        """
        Get the file extension corresponding to the given mime-type.

        mimeType:   Mime-type (string).

        Returns:    Extension corresponding to mime-type (string).
        """
        try:
            return self.__mimeType2ExtDic[mimeType]
        except:
            return NGAMS_UNKNOWN_MT


    def getMimeTypeFromExt(self,
                           extension):
        """
        Get the mime-type  corresponding to the given file extension.

        extension:    Extension of file (string).

        Returns:      Mime-type corresponding to extension (string).
        """
        try:
            return self.__ext2MimeTypeDic[extension]
        except:
            return NGAMS_UNKNOWN_MT


    def getMimeTypeMappings(self):
        """
        Return list containing sub-lists, one for each mime-type/extension
        mapping. The format is: [[mime-type, ext], [mime-type, ext], ...].

        Returns:    List with mime-type mappings ([[mt, ext], [mt, ext], ...]).
        """
        mappingsList = []
        for mt in self.__mimeType2ExtDic.keys():
            ext = self.__mimeType2ExtDic[mt]
            mappingsList.append([mt, ext])
        return mappingsList


    def getStorageSetList(self):
        """
        Get reference to list with Storage Set objects.

        Returns:  List with storage set objects ([ngamsStorageSet, ...]).
        """
        return self.__storageSetList


    def addStorageSetObj(self,
                         storageSetObj):
        """
        Add a Storage Set object to the configuration.

        storageSetObj:  Instance of Storage Set class (ngamsStorageSet).

        Returns:        Reference to object itself.
        """
        self.__storageSetList.append(storageSetObj)
        return self


    def getStorageSetFromId(self,
                            storageSetId):
        """
        Return a Storage Set object from a given Storage Set ID.

        storageSetId:     Storage Set ID (string).

        Returns:          Instance of ngamsStorageSet or
                          None (ngamsStorageSet | None).
        """
        T = TRACE()

        logger.debug("Finding storage set for ID: %s ...", storageSetId)
        reqSet = None
        for set in self.__storageSetList:
            if (set.getStorageSetId() == storageSetId):
                reqSet = set
                break
        return reqSet


    def getStorageSetFromSlotId(self,
                                slotId):
        """
        Get a Storage Set object from a given Slot ID.

        slotId:       Slot ID (string).

        Returns:      Instance of ngamsStorageSet or
                      None (ngamsStorageSet | None).
        """
        T = TRACE()

        for set in self.getStorageSetList():
            if ((set.getMainDiskSlotId() == slotId) or \
                (set.getRepDiskSlotId() == slotId)):
                return set
        # Raise exception.
        errMsg = genLog("NGAMS_ER_NO_STORAGE_SET", [slotId, self.getCfg()])
        raise Exception, errMsg


    def getAssocSlotId(self,
                       slotId):
        """
        Get the Slot ID of the disk associated to the disk with the
        given Slot ID.

        slotId:       Slot ID (string).

        Returns:      Slot ID of associated disk - "" if not found (string).
        """
        for set in self.getStorageSetList():
            if (set.getMainDiskSlotId() == slotId):
                return set.getRepDiskSlotId()
            elif (set.getRepDiskSlotId() == slotId):
                return set.getMainDiskSlotId()
        return ""


    def getSlotIds(self):
        """
        Return tuple with Slot IDs. The format is:

          [<Main Slot ID 1>,[ <Rep. Slot ID 1>,] <Main Slot ID 2>, ...]

        Returns:     Tuple with Slot IDs (tuple).
        """
        slotIdLst = []
        for set in self.getStorageSetList():
            if (set.getMainDiskSlotId().strip()):
                slotIdLst.append(set.getMainDiskSlotId())
            if (set.getRepDiskSlotId().strip()):
                slotIdLst.append(set.getRepDiskSlotId())
        return slotIdLst


    def getSlotIdDefined(self,
                         slotId):
        """
        Returns 1 if the Slot ID indicated is used in one of the
        Storage Sets defined, otherwise 0 is returned.

        slotId:            Slot ID (string).

        Returns:           1 if Slot ID is defined, otherwise 0 (integer/0|1).
        """
        return slotId in self.getSlotIds()


    def getPathPrefix(self):
        """
        Return Path Prefix.

        Returns:     Path Prefix (string).
        """
        return self.getVal("ArchiveHandling[1].PathPrefix")

    def getDataMoverSuspenstionTime(self):
        """
        Return the Data Mover (Subscription) Thread Suspension Time.

        Returns:         Suspension time (string/ISO 8601).
        """
        return self.getVal("DataMoverOnly[1].SuspensionTime")

    def getDataMoverHostIds(self):
        """
        """
        return self.getVal("DataMoverOnly[1].FromHostIds")

    def getNGASJobMANHost(self):
        """
        """
        return self.getVal("NGASJobMAN[1].host")

    def getChecksumPlugIn(self):
        """
        Return Checksum Plug-In.

        Returns:     Checksum Plug-In (string).
        """
        return self.getVal("DataCheckThread[1].ChecksumPlugIn")


    def getChecksumPlugInPars(self):
        """
        Return the Checksum Plug-In input parameters.

        Returns:     Checksum Plug-In parameters(string).
        """
        return self.getVal("DataCheckThread[1].ChecksumPlugInPars")


    def getDataCheckActive(self):
        """
        Return the Data Check Service enable/disable flag.

        Returns:     Data Check Service enabled/disabled (integer).
        """
        par = "DataCheckThread[1].Active"
        return getInt(par, self.getVal(par))


    def getDataCheckForceNotif(self):
        """
        Return the Force Data Check Notification Flag.

        Returns:       Force notification = 1 (integer/0|1).
        """
        par = "DataCheckThread[1].ForceNotif"
        return getInt(par, self.getVal(par))


    def getDataCheckMaxProcs(self):
        """
        Return the maximum number of parallel Data Check sub-processes.

        Returns:     Maximum number of sub-processes (integer).
        """
        par = "DataCheckThread[1].MaxProcs"
        return getInt(par, self.getVal(par))


    def getDataCheckScan(self):
        """
        Return the Data Check Scan Flag.

        Returns:     Data Check Scan Flag (integer/0|1).
        """
        par = "DataCheckThread[1].Scan"
        return getInt(par, self.getVal(par), 1)


    def getDataCheckMinCycle(self):
        """
        Return the Data Check Service Minimum Cycle Time.

        Returns:     Data Check  Minimum Cycle Time (string).
        """
        return self.getVal("DataCheckThread[1].MinCycle")


    def getStreamList(self):
        """
        Get list containing the Stream objects

        Returns:   List containing Stream objects ([ngamsStream, ...]).
        """
        return self.__streamList


    def getStreamFromMimeType(self,
                              mimeType):
        """
        Get an ngamsStream object from its mime-type.

        mimeType:   Mime-type for Stream (string).

        Returns:    Stream object or None (ngamsStream|None).
        """
        T = TRACE()

        logger.debug("Finding stream for  mime-type: %s ...", mimeType)
        for stream in self.getStreamList():
            if (stream.getMimeType() == mimeType):
                return stream
        return None


    def addStreamObj(self,
                     streamObj):
        """
        Add an ngamsStream object.

        streamObj:   Stream object (ngamsStream).

        Returns:     Reference to object itself.
        """
        self.__streamList.append(streamObj)
        return self


    def getMinFreeSpaceWarningMb(self):
        """
        Get the limit for the minimum free space available, before
        a warning is issued to change the disk.

        Returns:   Minimum free space before issuing warning (integer).
        """
        par = "ArchiveHandling[1].MinFreeSpaceWarningMb"
        return getInt(par, self.getVal(par))


    def getFreeSpaceDiskChangeMb(self):
        """
        Get the limit for the minimum free disk space before
        changing disk.

        Returns:  MB limit for changing disk (integer).
        """
        par = "ArchiveHandling[1].FreeSpaceDiskChangeMb"
        return getInt(par, self.getVal(par))


    def getSysLog(self):
        """
        Return the syslog on/off flag.

        Returns:   Syslog on/off flag (integer).
        """
        par = "Log[1].SysLog"
        return getInt(par, self.getVal(par))


    def getSysLogPrefix(self):
        """
        Return the syslog prefix.

        Returns:  Syslog prefix (string).
        """
        return self.getVal("Log[1].SysLogPrefix")


    def getSysLogAddress(self):
        """
        Return the address where syslog is listening for incoming messages.
        If no address is given, a platform-dependent default is used

        Returns:  Syslog address (string).
        """
        return self.getVal("Log[1].SysLogAddress")


    def getLocalLogFile(self):
        """
        Return the Local Log File.

        Returns:  Name of Local Log File (string).
        """
        logFile = self.getVal("Log[1].LocalLogFile")
        if logFile and logFile[0] != '/':
            logFile = self.getRootDirectory() + '/' + logFile
        return logFile


    def getLocalLogLevel(self):
        """
        Return the Local Log Level.

        Returns:  Local Log Level (integer).
        """
        par = "Log[1].LocalLogLevel"
        return getInt(par, self.getVal(par))


    def getLogBufferSize(self):
        """
        Return the size of the internal log buffer.

        Returns:  Size of internal log buffer (integer).
        """
        par = "Log[1].LogBufferSize"
        return getInt(par, self.getVal(par))


    def getLogRotateInt(self):
        """
        Return the Log Rotation Interval given as an ISO 8601 timestamp.

        Returns:       Log Rotation Interval as ISO 8601 format (string).
        """
        return self.getVal("Log[1].LogRotateInt")


    def getLogRotateCache(self):
        """
        Return the size of the internal log rotation cache.

        Returns:  Size of internal log buffer (integer).
        """
        par = "Log[1].LogRotateCache"
        return getInt(par, self.getVal(par))


    def getArchiveRotatedLogfiles(self):
        """Whether rotated logfiles are automatically archived locally or not"""
        par = "Log[1].ArchiveRotatedLogfiles"
        return getInt(par, self.getVal(par), 0)


    def getNotifSmtpHost(self):
        """
        Return the SMTP Host for sending Notification e-mails.

        Returns:   SMTP Host (string).
        """
        return self.getVal("Notification[1].SmtpHost")


    def getNotifActive(self):
        """
        Return the Email Notification Active Flag.

        Returns:   Notification Active Flag (integer)
        """
        par = "Notification[1].Active"
        return getInt(par, self.getVal(par))


    def getMaxRetentionTime(self):
        """
        Return the Maximum Retention Time, which is the maximum time an
        Email Notification Message should be retained before it is send out.


        Returns:       Maximum Retention Time as ISO 8601 format (string).
        """
        return self.getVal("Notification[1].MaxRetentionTime")


    def getSender(self):
        """
        Return the senders email address. This is important in cases where
        the smtp server is setup to allow emails only from known domains
        and the NGAS server sits on a private network.

        Returns:       email address for the 'from' field (string).
        """
        return self.getVal("Notification[1].Sender")


    def getMaxRetentionSize(self):
        """
        Get the Maximum Retention Size, which is the maximum number of
        Email Notification Messages, which is kept before sending these out.

        Returns:      Maximum retention buffer size (integer).
        """
        par = "Notification[1].MaxRetentionSize"
        return getInt(par, self.getVal(par))


    def getAlertNotifList(self):
        """
        Get reference to tuple with recipients of
        Alert Notification Events.

        Returns:  Tuple with recipients (tuple).
        """
        return self.__alertNotif


    def getErrorNotifList(self):
        """
        Get reference to tuple with recipients of
        Error Notification Events.

        Returns:  Tuple with recipients (tuple).
        """
        return self.__errorNotif


    def getDiskSpaceNotifList(self):
        """
        Get reference to tuple with recipients of
        Disk Space Notification Events.

        Returns:  Tuple with recipients (tuple).
        """
        return self.__diskSpaceNotif


    def setDiskSpaceNotifList(self,
                              subscriberList):
        """
        Set the list of Disk Space Notification Subscribers.

        subscriberList:   List of subscribers of the Disk Change
                          Notification (list).

        Returns:          Reference to object itself.
        """
        self.__diskSpaceNotif = subscriberList
        # Update also the XML Manager.
        xmlPath = "NgamsCfg.Notification[1].DiskSpaceNotification[1]." +\
                  "EmailRecipient[%d].Address"
        for idx in range(len(subscriberList)):
            self.__cfgMgr.storeVal(xmlPath % (idx + 1), subscriberList[idx])
        return self


    def setDiskChangeNotifList(self,
                               subscriberList):
        """
        Set the list of Disk Change Notification Subscribers.

        subscriberList:   List of subscribers of the Disk Change
                          Notification (list).

        Returns:          Reference to object itself.
        """
        self.__diskChangeNotif = subscriberList
        # Update also the XML Manager.
        xmlPath = "NgamsCfg.Notification[1].DiskChangeNotification[1]." +\
                  "EmailRecipient[%d].Address"
        for idx in range(len(subscriberList)):
            self.__cfgMgr.storeVal(xmlPath % (idx + 1), subscriberList[idx])
        return self


    def getDiskChangeNotifList(self):
        """
        Get reference to tuple with recipients of
        Disk Change Notification Events.

        Returns:  Tuple with recipients (tuple).
        """
        return self.__diskChangeNotif


    def getNoDiskSpaceNotifList(self):
        """
        Get reference to tuple with recipients of
        No Free Disks Notification Events.

        Returns:  Tuple with recipients (tuple).
        """
        return self.__noDiskSpaceNotif


    def getDataCheckNotifList(self):
        """
        Get reference to tuple with recipients of Data Check Notification
        Messages.

        Returns:  Tuple with recipients (tuple).
        """
        return self.__dataCheckNotif


    def getIdleSuspension(self):
        """
        Return the NGAS Idle Suspension Flag.

        Returns:     Idle Suspension Flag (integer/0|1).
        """
        par = "HostSuspension[1].IdleSuspension"
        return getInt(par, self.getVal(par))


    def getIdleSuspensionTime(self):
        """
        Return the Idle Suspension Time.

        Returns:         Idle Suspension Time in seconds (integer).
        """
        par = "HostSuspension[1].IdleSuspensionTime"
        suspTime = getInt(par, self.getVal(par))

        # Small security to avoid suspension time of 0s, we do not allow
        # a suspension time less than 60s.
        if suspTime <= 0 and self.getIdleSuspension():
            msg = "Suspension Timeout must be > 0. " +\
                  "Specified: %ds. Setting to minimum value."
            logger.warning(msg, suspTime)
            suspTime = 60
        return suspTime


    def getWakeUpServerHost(self):
        """
        Return the Wake-Up Server host name.

        Returns:   Name of Wake-up Server Host (string).
        """
        return self.getVal("HostSuspension[1].WakeUpServerHost")


    def getSuspensionPlugIn(self):
        """
        Return the name of the Suspension Plug-In.

        Returns:   Name of plug-in (string).
        """
        return self.getVal("HostSuspension[1].SuspensionPlugIn")


    def getSuspensionPlugInPars(self):
        """
        Return the Suspension Plug-In parameters.

        Returns:   Plug-in parameters (string).
        """
        return self.getVal("HostSuspension[1].SuspensionPlugIn")


    def getWakeUpPlugIn(self):
        """
        Return the name of the Wake-Up Plug-In.

        Returns:   Name of plug-in (string).
        """
        return self.getVal("HostSuspension[1].WakeUpPlugIn")


    def getWakeUpPlugInPars(self):
        """
        Return the parameters to the Wake-Up Plug-In.

        Returns:   Plug-in parameters (string).
        """
        return self.getVal("HostSuspension[1].WakeUpPlugInPars")


    def getWakeUpCallTimeOut(self):
        """
        Return the Wake-Up Call Time-Out for waiting for an NGAS host
        being woken up to be up and running.

        Returns:   Time-out in seconds (integer).
        """
        par = "HostSuspension[1].WakeUpCallTimeOut"
        return getInt(par, self.getVal(par))


    def getAutoUnsubscribe(self):
        """
        Return the Auto-Unsubscribe Flag.

        Returns:    Auto Un-Subscribe Flag (integer/0|1).
        """
        par = "SubscriptionDef[1].AutoUnsubscribe"
        return getInt(par, self.getVal(par))


    def getSubscrSuspTime(self):
        """
        Return the Subscription Thread Suspension Time.

        Returns:         Suspension time (string/ISO 8601).
        """
        return self.getVal("SubscriptionDef[1].SuspensionTime")


    def getBackLogExpTime(self):
        """
        Return the expiration time for directories and files in the
        Subscription Back-Log Area.

        Returns:         Expiration time (string/ISO 8601).
        """
        return self.getVal("SubscriptionDef[1].BackLogExpTime")


    def getSubscrEnable(self):
        """
        Return the Susbcription Enable/Disable Flag to switch on/off the
        subscription for data from data providers.

        Returns:         1 = enabled, 0 = disabled (integer/0|1).
        """
        par = "SubscriptionDef[1].Enable"
        return getInt(par, self.getVal(par))


    def getSubscriptionsDic(self):
        """
        Get reference to list with Subscriptions Objects.

        Returns:    Subscriber List (list/ngamsSubscriber).
        """
        return self.__subscriptionsDic

    def getFileStagingEnable(self):
        """
        Return if the file staging flag is set to Enabled / Disable

        Returns:    1 = enabled, 0 = disabled (integer/0|1)
        """
        par = "FileStagingDef[1].Enable"
        strVal = self.getVal(par)
        if (not strVal):
            return 0
        return getInt(par, strVal)

    def getFileStagingPlugInHost(self):
        par = "FileStagingDef[1].Host"
        return self.getVal(par)

    def getFileStagingPlugInPort(self):
        par = "FileStagingDef[1].Port"
        return self.getVal(par)

    def getFileStagingPlugIn(self):
        """
        Return the name of the FileStagingPlugIn,
        which takes file online if it is offline.

        The plugin must contain these two functions:

        def isFileOffline(filename)
            PAR: filename: string
            RETURN: 1 - yes, 0 - no, Exception - error

        def stageFiles(filenameList)
            PAR: filenameList: List of file names (string)
            RETURN:   the number of files staged. Exception, if any errors
        """
        par = "FileStagingDef[1].PlugIn"
        return self.getVal(par)


    def getAuthorize(self):
        """
        Return the authorization flag.

        Returns:    1 = authorization on (integer/0|1).
        """
        par = "Authorization[1].Enable"
        return getInt(par, self.getVal(par))


    def getAuthUsers(self):
        """
        Return the defined users.

        Returns:   List with user names (list).
        """
        return self.__authUserDic.keys()


    def addAuthUser(self,
                    user,
                    password):
        """
        Add a user in the object.

        user:         User name (string).

        password:     Encrypted password (string).

        Returns:      Reference to object itself.
        """
        self.__authUserDic[user] = password
        return self

    def addAuthUserCommands(self, user, commands):
        """
        Add a user in the object.

        user:         User name (string).

        commands:     comma separated commands (string). e.g. RETRIEVE,STATUS,QARCHIVE
                      a "*" means all commands

        Returns:      Reference to object itself.
        """
        if (commands):
            self.__authUserCommandsDic[user] = commands.upper()
        return self


    def hasAuthUser(self,
                    user):
        """
        Check if a user with the given ID is defined.

        user:      User name (string).

        Returns:   1 = user defined (integer/0|1).
        """
        if (self.__authUserDic.has_key(user)):
            return 1
        else:
            return 0


    def getAuthUserInfo(self,
                        user):
        """
        Returns the info (password) for a user.

        user:      User name (string).

        Returns:   Password or None (string).
        """
        if (not self.__authUserDic.has_key(user)):
            return None
        else:
            return self.__authUserDic[user]

    def getAuthUserCommands(self, user):
        """
        Returns the info (password) for a user.

        user:      User name (string).

        Returns:   Password or None (string).
        """
        if (not self.__authUserCommandsDic.has_key(user)):
            return None
        else:
            return self.__authUserCommandsDic[user]


    def getAuthHttpHdrVal(self,
                          user = None):
        """
        Generate the value to be sent with the HTTP Autorization Header.
        If no specific user is given, an arbitrary user is chosen.

        user:        Name of registered user (string|None).

        Returns:     Authorization HTTP Header value (string).
        """
        if (not user): user = self.getAuthUsers()[0]
        if (not self.__authUserDic.has_key(user)):
            raise Exception, "Undefined user referenced: %s" % user
        pwd = base64.b64decode(self.getAuthUserInfo(user))
        authHdrVal = "Basic " + base64.b64encode(user + ":" + pwd)
        return authHdrVal


    def getMirroringActive(self):
        """
        Return the flag indicating if the Mirroring Service is activated.

        Returns:    Value of mirroring activated flag (integer).
        """
        try:
            return int(self.getVal("Mirroring[1].Active"))
        except:
            return 0


    def getMirroringThreads(self):
        """
        Return the number of mirroring threads to use.

        Returns:    Number of mirroring threads (integer).
        """
        return int(self.getVal("Mirroring[1].Threads"))


    def getMirroringReportRecipients(self):
        """
        Return the report recipients list.

        Returns:    The list of report recipients.
        """
        return self.getVal("Mirroring[1].ReportRecipients")


    def getMirroringErrorRetryPeriod(self):
        """
        Return the period for retrying to mirroring failing requests.

        Returns:    Error retry timeout (integer).
        """
        return int(self.getVal("Mirroring[1].ErrorRetryPeriod"))


    def getMirroringErrorRetryTimeOut(self):
        """
        Return the timeout for retrying to mirror a failing request.

        Returns:    Error retry timeout (integer).
        """
        return int(self.getVal("Mirroring[1].ErrorRetryTimeOut"))


    def addMirroringSrcObj(self,
                           mirSrcObj):
        """
        Add a new Mirroring Source Object in the internal list.

        mirSrcObj:  Mirroring Source Object (ngamsMirroringSource).

        Returns:    Reference to object itself.
        """
        self.__mirSrcObjList.append(mirSrcObj)
        self.__mirSrcObjDic[mirSrcObj.getId()] = mirSrcObj
        self.__mirSrcObjDic[mirSrcObj.getServerList()] = mirSrcObj
        return self


    def getMirroringSrcObj(self,
                           id):
        """
        Find the Mirroring Source Object with the given ID.

        id:        ID associated to the Mirroring Source Object (string).

        Returns:   Reference to Mirroring Source Object in question
                   (ngamsMirroringSource).
        """
        T = TRACE()

        if (not self.__mirSrcObjDic.has_key(id)):
            msg = "No Mirroring Source found in configuration with ID: %s"
            raise Exception, msg % id
        else:
            return self.__mirSrcObjDic[id]


    def getMirroringSrcObjFromSrvList(self,
                                      srvList):
        """
        Return the Mirroring Source Object associated to the given
        Server List.

        srvList:     Server list, common separated list of

                       '<Node>:<Port,...'                          (string).

        Returns:     Reference to Mirroring Source Object associated to the
                     given server list (ngamsMirroringSource).
        """
        T = TRACE()

        if (not self.__mirSrcObjDic.has_key(srvList)):
            msg = "No Mirroring Source Object found for Server List: %s"
            raise Exception, msg % srvList
        else:
            return self.__mirSrcObjDic[srvList]


    def getMirroringSrcList(self):
        """
        Get reference to list with Mirroring Source Objects.

        Returns:  List with Mirroring Source Objects
                  ([ngamsMirroringSource, ...]).
        """
        return self.__mirSrcObjList


    def getCachingPeriod(self):
        """
        Return the period for checking the cache holding.

        Returns:    Value of caching period (integer).
        """
        try:
            return isoTime2Secs(self.getVal("Caching[1].Period"))
        except:
            return 0


    def _check(self):
        """
        Check some parameters in the configuration.

        NOTE: A validating XML parser + XML Schema should be used when loading
              the configuration. In this case this function is nolonger needed.

        Returns:  Void.
        """
        T = TRACE()

        logger.debug("Check Server Element ...")
        checkIfSetStr("Server.ArchiveName", self.getArchiveName(),
                      self.getCheckRep())
        checkIfSetInt("Server.MaxSimReqs", self.getMaxSimReqs(),
                      self.getCheckRep())
        checkIfSetInt("Server.PortNo", self.getPortNo(), self.getCheckRep())
        if (self.getAllowArchiveReq()):
            checkIfZeroOrOne("Server.Replication", self.getReplication(),
                             self.getCheckRep())
        checkIfSetInt("Server.BlockSize", self.getBlockSize(),
                      self.getCheckRep())
        if (self.getSwVersion()):
            if ((self.getSwVersion().strip() != "") and
                (self.getSwVersion().strip() != getNgamsVersionRaw().strip())):
                errMsg = "The SW Version defined in the NG/AMS " +\
                         "Configuration: " + self.getSwVersion() + " " +\
                         "is not compatible with the SW Version of the " +\
                         "NG/AMS installation used: " + getNgamsVersionRaw() +\
                         ". Configuration parameter: Server.SwVersion."
                errMsg = genLog("NGAMS_ER_CONF_PROP", [errMsg])
                raise Exception, errMsg
        checkIfZeroOrOne("Server.Simulation", self.getSimulation(),
                         self.getCheckRep())
        if (checkIfSetStr("Server.RootDirectory",
                          self.getRootDirectory(), self.getCheckRep())):
            # Check if a legal root directory specified.
            if (not os.path.exists(self.getRootDirectory())):
                try:
                    checkCreatePath(self.getRootDirectory())
                except:
                    errMsg = genLog("NGAMS_ER_ILL_ROOT_DIR",
                                    [self.getCfg(), self.getRootDirectory()])
                    logger.exception(errMsg)
                    self.getCheckRep().append(errMsg)
        checkIfZeroOrOne("Server.ProxyMode", self.getProxyMode(),
                         self.getCheckRep())
        logger.debug("Checked Server Element")

        logger.debug("Check SystemPlugIns Element ...")
        checkIfSetStr("SystemPlugIns.OnlinePlugIn",
                      self.getOnlinePlugIn(), self.getCheckRep())
        checkIfSetStr("SystemPlugIns.OfflinePlugIn", self.getOfflinePlugIn(),
                      self.getCheckRep())
        logger.debug("Checked SystemPlugIns Element")

        logger.debug("Check Permissions Element ...")
        checkIfZeroOrOne("Permissions.AllowArchiveReq",
                         self.getAllowArchiveReq(), self.getCheckRep())
        checkIfZeroOrOne("Permissions.AllowRetrieveReq",
                         self.getAllowRetrieveReq(), self.getCheckRep())
        checkIfZeroOrOne("Permissions.AllowProcessingReq",
                         self.getAllowProcessingReq(), self.getCheckRep())
        checkIfZeroOrOne("Permissions.AllowRemoveReq",
                         self.getAllowRemoveReq(), self.getCheckRep())
        logger.debug("Checked Permissions Element")

        logger.debug("Check JanitorThread Element ...")
        checkIfSetStr("JanitorThread.SuspensionTime",
                      self.getJanitorSuspensionTime(), self.getCheckRep())
        logger.debug("Checked JanitorThread Element")

        logger.debug("Check ArchiveHandling Element ...")
        if (self.getAllowArchiveReq()):
            checkIfSetStr("ArchiveHandling.PathPrefix", self.getPathPrefix(),
                          self.getCheckRep())
            checkIfZeroOrOne("ArchiveHandling.BackLogBuffering",
                             self.getBackLogBuffering(), self.getCheckRep())
            checkIfSetStr("ArchiveHandling.BackLogBufferDirectory",
                          self.getBackLogBufferDirectory(), self.getCheckRep())
            checkIfSetInt("ArchiveHandling.MinFreeSpaceWarningMb",
                          self.getMinFreeSpaceWarningMb(), self.getCheckRep())
            checkIfSetInt("ArchiveHandling.FreeSpaceDiskChangeMb",
                          self.getFreeSpaceDiskChangeMb(), self.getCheckRep())
        logger.debug("Checked ArchiveHandling Element")

        logger.debug("Check Db Element ...")
        checkIfZeroOrOne("Db.Snapshot",self.getDbSnapshot(),self.getCheckRep())
        checkIfSetStr("Db.Interface",self.getDbInterface(), self.getCheckRep())
        logger.debug("Checked Db Element")

        logger.debug("Check MimeTypes Element ...")
        if (len(self.getMimeTypeMappings()) == 0):
            errMsg = genLog("NGAMS_ER_NO_MIME_TYPES", [self.getCfg()])
            logger.error(errMsg)
            self.getCheckRep().append(errMsg)
        else:
            for map in self.getMimeTypeMappings():
                checkIfSetStr("MimeTypeMap.MimeType",map[0],self.getCheckRep())
                checkIfSetStr("MimeTypeMap.Extension", map[1],
                              self.getCheckRep())
        logger.debug("Checked MimeTypes Element")

        logger.debug("Check Storage Sets ...")
        storageSetDic = {}
        mainDiskMtPtDic = {}
        repDiskMtPtDic = {}
        for set in self.getStorageSetList():
            checkIfSetStr("StorageSet.StorageSetId", set.getStorageSetId(),
                          self.getCheckRep())
            checkDuplicateValue(storageSetDic, "StorageSet.StorageSetId",
                                set.getStorageSetId(), self.getCheckRep())
            checkIfSetStr("StorageSet.MainDiskSlotId",
                          set.getMainDiskSlotId(), self.getCheckRep())
            checkDuplicateValue(mainDiskMtPtDic, "StorageSet.MainDiskSlotId",
                                set.getMainDiskSlotId(),self.getCheckRep())
            if (set.getRepDiskSlotId() != ""):
                checkDuplicateValue(repDiskMtPtDic, "StorageSet.RepDiskSlotId",
                                    set.getRepDiskSlotId(),
                                    self.getCheckRep())
            checkIfZeroOrOne("StorageSet.Mutex", set.getMutex(),
                             self.getCheckRep())
        logger.debug("Checked Storage Sets")

        logger.debug("Check Stream Definitions ...")
        if (self.getAllowArchiveReq()):
            mimeTypeDic = {}
            for stream in self.getStreamList():
                checkIfSetStr("Stream.MimeType", stream.getMimeType(),
                              self.getCheckRep())
                checkDuplicateValue(mimeTypeDic, "Stream.MimeType",
                                    stream.getMimeType(), self.getCheckRep())
                if ((len(stream.getStorageSetIdList()) == 0) and
                    (len(stream.getHostIdList()) == 0)):
                    errMsg = "Must specify at least one Target Storage Set " +\
                             "or Archiving Unit for each Stream!"
                    errMsg = genLog("NGAMS_ER_CONF_FILE", [errMsg])
                    logger.error(errMsg)
                    self.getCheckRep().append(errMsg)
                for setId in stream.getStorageSetIdList():
                    if (not storageSetDic.has_key(setId)):
                        errMsg = "Undefined Storage Set Id: "+str(setId)+" " +\
                                 "referenced in definition of Target " +\
                                 "Storage Set for Stream with mime-type: " +\
                                 stream.getMimeType()
                        errMsg = genLog("NGAMS_ER_CONF_FILE", [errMsg])
                        logger.error(errMsg)
                        self.getCheckRep().append(errMsg)
        logger.debug("Checked Stream Definitions")

        logger.debug("Check Processing Element ...")
        if (self.getAllowProcessingReq()):
            checkIfSetStr("Processing.ProcessingDirectory",
                          self.getProcessingDirectory(), self.getCheckRep())
            if (self.getProcessingDirectory()):
                procDir = os.path.normpath(self.getProcessingDirectory()+"/" +\
                                           NGAMS_PROC_DIR)
                if (not os.path.exists(procDir)):
                    try:
                        os.makedirs(procDir)
                    except Exception, e:
                        errMsg = genLog("NGAMS_ER_ILL_PROC_DIR",
                                        [self.getCfg(),
                                         self.getProcessingDirectory()])
                        logger.error(errMsg)
                        self.getCheckRep().append(errMsg)
        for dppi_plugin in self.dppi_plugins.values():
            checkIfSetStr("Processing.PlugIn.Name", dppi_plugin.name,
                          self.getCheckRep())
            for mimeType in dppi_plugin.mime_types:
                checkIfSetStr("Processing.PlugIn.MimeType.Name", mimeType,
                              self.getCheckRep())
        logger.debug("Checked Processing Element")

        logger.debug("Check Register Element ...")
        for reg_plugin in self.register_plugins.values():
            checkIfSetStr("Register.PlugIn.Name", reg_plugin.name, self.getCheckRep())
        logger.debug("Checked Register Element")

        logger.debug("Check DataCheckThread Element ...")
        checkIfZeroOrOne("DataCheckThread.DataCheckActive",
                         self.getDataCheckActive(), self.getCheckRep())
        if (self.getDataCheckActive()):
            checkIfSetStr("DataCheckThread.ChecksumPlugIn",
                          self.getChecksumPlugIn(), self.getCheckRep())
            checkIfZeroOrOne("DataCheckThread.DataCheckForceNotif",
                             self.getDataCheckForceNotif(), self.getCheckRep())
            checkIfSetInt("DataCheckThread.DataCheckMaxProcs",
                          self.getDataCheckMaxProcs(), self.getCheckRep())
            checkIfZeroOrOne("DataCheckThread.DataCheckScan",
                             self.getDataCheckScan(), self.getCheckRep())
            checkIfSetStr("DataCheckThread.DataCheckMinCycle",
                          self.getDataCheckMinCycle(), self.getCheckRep())
        logger.debug("Checked DataCheckThread Element")

        logger.debug("Check Log Element ...")
        checkIfZeroOrOne("Log.SysLog", self.getSysLog(), self.getCheckRep())
        checkIfSetStr("Log.SysLogPrefix", self.getSysLogPrefix(),
                      self.getCheckRep())
        checkIfSetStr("Log.LocalLogFile", self.getLocalLogFile(),
                      self.getCheckRep())
        checkIfSetInt("Log.LocalLogLevel", self.getLocalLogLevel(),
                      self.getCheckRep())
        checkIfSetStr("Log.LogRotateInt/ISO 8601", self.getLogRotateInt(),
                      self.getCheckRep())
        checkIfSetInt("Log.LogRotateCache", self.getLogRotateCache(),
                      self.getCheckRep())
        logger.debug("Checked Log Element")

        logger.debug("Check Notification Element ...")
        checkIfSetStr("Notification.SmtpHost", self.getNotifSmtpHost(),
                      self.getCheckRep())
        checkIfSetStr("Notification.Sender", self.getSender(),
                      self.getCheckRep())
        checkIfZeroOrOne("Notification.Active", self.getNotifActive(),
                         self.getCheckRep())
        checkIfSetStr("Notification.MaxRetentionTime",
                      self.getMaxRetentionTime(), self.getCheckRep())
        checkIfSetInt("Notification.MaxRetentionSize",
                      self.getMaxRetentionSize(), self.getCheckRep())
        logger.debug("Checked Notification Element")

        logger.debug("Check HostSuspension Element ...")
        checkIfZeroOrOne("HostSuspension.IdleSuspension",
                         self.getIdleSuspension(), self.getCheckRep())
        checkIfSetInt("HostSuspension.IdleSuspensionTime",
                      self.getIdleSuspensionTime(), self.getCheckRep())
        checkIfSetStr("HostSuspension.SuspensionPlugIn",
                      self.getSuspensionPlugIn(), self.getCheckRep())
        checkIfSetStr("HostSuspension.SuspensionPlugInPars",
                      self.getSuspensionPlugInPars(), self.getCheckRep())
        checkIfSetInt("HostSuspension.WakeUpCallTimeOut",
                      self.getWakeUpCallTimeOut(), self.getCheckRep())
        checkIfSetStr("HostSuspension.WakeUpPlugIn",
                      self.getWakeUpPlugIn(), self.getCheckRep())
        if (self.getIdleSuspension()):
            checkIfSetStr("HostSuspension.WakeUpServerHost",
                          self.getWakeUpServerHost(), self.getCheckRep())
        logger.debug("Checked HostSuspension Element")

        logger.debug("Check SubscriptionDef Element ...")
        checkIfZeroOrOne("SubscriptionDef.AutoUnsubscribe",
                         self.getAutoUnsubscribe(), self.getCheckRep())
        checkIfSetStr("SubscriptionDef.SuspensionTime",
                      self.getSubscrSuspTime(), self.getCheckRep())
        checkIfSetStr("SubscriptionDef.BackLogExpTime",
                      self.getBackLogExpTime(), self.getCheckRep())
        checkIfZeroOrOne("SubscriptionDef.Enable", self.getSubscrEnable(),
                         self.getCheckRep())
        logger.debug("Checked SubscriptionDef Element")

        logger.debug("Check Mirroring Element ...")
        # TODO: Implement.
        logger.debug("Checked Mirroring Element")

        logger.debug("Check Caching Element ...")
        # Cannot have Remove Requests disabled and Cahcing
        if ((not self.getAllowRemoveReq()) and (self.getCachingActive())):
            msg = "Permission to execute Remove Requests must be switched " +\
                  "on in order to enable the Caching Service"
            raise Exception, msg
        # TODO: More checks.
        logger.debug("Checked Caching Element")

        # Any errors found?
        if (len(self.getCheckRep()) > 0):
            testRep = self.genCheckRep()
            raise Exception, testRep

        return self


    def save(self,
             targetFilename,
             hideCritInfo = 1):
        """
        Save the configuration in the object into a XML document
        with the given name.

        targetFilename:    Name of target file (string).

        hideCritInfo:      If set to 1 passwords and other 'confidential'
                           information appearing in the log file, will
                           be hidden (integer/0|1).

        Returns:           Reference to object itself.
        """
        T = TRACE()

        self.__cfgMgr.save(targetFilename, hideCritInfo)
        return self


    def genXml(self,
               hideCritInfo = 1):
        """
        Generate an XML DOM Node object from the contents of the
        ngamsConfig object.

        Returns:    XML DOM Node (Node).
        """
        T = TRACE()

        xmlDomObj = self.__cfgMgr.genXml(hideCritInfo)
        return xmlDomObj


    def genXmlDoc(self,
                  hideCritInfo = 1):
        """
        Generate an XML Document from the contents loaded in a string buffer
        and return this.

        hideCritInfo:   Hide critical information (integer/0|1).

        Returns:    XML document (string).
        """
        return self.__cfgMgr.genXmlDoc(hideCritInfo)


    def getCheckRep(self):
        """
        Return reference to Check Report (list with errors found in
        configuration file).

        Returns:   Reference to Check Report (list).
        """
        return self.__checkRep


    def genCheckRep(self,
                    sep = "; "):
        """
        Generate a Check Report from the errors stored in the object.

        sep:       Sepator used to separate each item in the report (string).

        Returns:   Check Report (string).
        """
        testRep = "CHECK REPORT FOR NG/AMS CONFIGURATION" + sep
        testRep += "Configuration Filename: " + str(self.getCfg()) + sep
        for err in self.getCheckRep():
            testRep += err + sep
        testRep = testRep[0:-2]
        return testRep


    def getBackLogDir(self):
        """
        Return the exact (complete) name of the Back-Log Buffer Directory.

        Returns:    Name of Back-Log Buffer Directory (string).
        """
        return os.path.normpath(self.getBackLogBufferDirectory() + "/" +\
                                NGAMS_BACK_LOG_DIR)

    def getRequestDbBackend(self):
        """
        Returns whether the server should keep a request database or not.
        """
        val = self.getVal("Server[1].RequestDbBackend")

        # Check and normalize
        allowed_values = (None, '', 'null', 'bsddb', 'memory')
        if val not in allowed_values:
            raise Exception('RequestDbBackend %s not one of %s' % (val, allowed_values))
        if not val:
            val = 'null'

        return val