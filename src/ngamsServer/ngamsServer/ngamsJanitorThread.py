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
# "@(#) $Id: ngamsJanitorThread.py,v 1.14 2010/03/25 14:47:44 jagonzal Exp $"
#
# Who       When        What
# --------  ----------  -------------------------------------------------------
# jknudstr  29/01/2002  Created
#
"""
This module contains the code for the Janitor Thread, which is used to perform
various background activities as cleaning up after processing, waking up
suspended NGAS hosts, suspending itself.
"""
# TODO: Give overhaul to handling of the DB Snapshot: Use ngamsDbm instead
#       of bsddb + simplify the algorithm.

import os, time, glob, cPickle
import math
import types
import shutil

import ngamsArchiveUtils, ngamsSrvUtils
from ngamsLib.ngamsCore import TRACE, info, \
    getFileCreationTime, getFileModificationTime, getFileAccessTime, rmFile, \
    warning, NGAMS_DB_DIR, NGAMS_DB_NGAS_FILES, checkCreatePath, \
    NGAMS_DB_CH_CACHE, getMaxLogLevel, NGAMS_NOTIF_DATA_CHECK, \
    NGAMS_TEXT_MT, NGAMS_PICKLE_FILE_EXT, NGAMS_DB_CH_FILE_DELETE, \
    NGAMS_DB_CH_FILE_INSERT, NGAMS_DB_CH_FILE_UPDATE, notice, error, \
    isoTime2Secs, genLog, NGAMS_PROC_DIR, NGAMS_SUBSCR_BACK_LOG_DIR, takeLogSem, \
    iso8601ToSecs, getLocation, logFlush, relLogSem, alert, \
    NGAMS_HTTP_INT_AUTH_USER, getHostName, NGAMS_OFFLINE_CMD, NGAMS_NOTIF_ERROR,\
    loadPlugInEntryPoint
from ngamsLib import ngamsFileInfo, ngamsNotification
from ngamsLib import ngamsDbm, ngamsDbCore, ngamsEvent, ngamsHighLevelLib, ngamsLib
from pccLog import PccLog
from pccUt import PccUtTime

try:
    import bsddb3 as bsddb
except ImportError:
    import bsddb



NGAMS_JANITOR_THR = "JANITOR-THREAD"

class StopJanitorThreadException(Exception):
    pass

def checkStopJanitorThread(stopEvt):
    """
    Checks if the Janitor Thread should be stopped, raising an exception if needed
    """
    if stopEvt.is_set():
        info(2,"Exiting Janitor Thread")
        raise StopJanitorThreadException()

def suspend(stopEvt, t):
    """
    Sleeps for at maximum ``t`` seconds, or until the Janitor Thread is signaled
    to stop
    """
    if stopEvt.wait(t):
        info(2,"Exiting Janitor Thread")
        raise StopJanitorThreadException()

def checkCleanDirs(startDir,
                   dirExp,
                   fileExp,
                   useLastAccess):
    """
    Check a tree of directories. Delete all empty directories older than
    the given Directory Expiration. Also files are deleted if the file is
    older than File Expiration given.

    startDir:       Starting directory. The function will move downwards from
                    this starting point (string).

    dirExp:         Expiration time in seconds for directories. Empty
                    directories older than this time are deleted (integer).

    fileExp:        Expiration time in seconds for file. Empty file older than
                    this time are deleted (integer).

    useLastAccess:  Rather than using the creation time as reference, the
                    last modification and access date should be used
                    (integer/0|1).

    Returns:        Void.
    """
    T = TRACE(5)

    timeNow = time.time()
    # TODO: Potential memory bottleneck. Use 'find > file' as for REGISTER
    #       Command.
    entryList = glob.glob(startDir + "/*")
    # Work down through the directories in a recursive manner. If some
    # directories are not deleted during this run because they have contents,
    # they might be deleted during one of the following runs.
    for entry in entryList:
        if (not useLastAccess):
            refTime = getFileCreationTime(entry)
        else:
            refTime1 = getFileModificationTime(entry)
            refTime2 = getFileAccessTime(entry)
            if (refTime1 > refTime2):
                refTime = refTime1
            else:
                refTime = refTime2
        if (os.path.isdir(entry)):
            checkCleanDirs(entry, dirExp, fileExp, useLastAccess)
            tmpGlobRes = glob.glob(entry + "/*")
            if (tmpGlobRes == []):
                if ((timeNow - refTime) > dirExp):
                    info(4,"Deleting temporary directory: " + entry)
                    rmFile(entry)
        else:
            if (fileExp):
                if ((timeNow - refTime) > fileExp):
                    info(4,"Deleting temporary file: " + entry)
                    rmFile(entry)


def _addInDbm(snapShotDbObj,
              key,
              val,
              sync = 0):
    """
    Add an entry in the DB Snapshot. This entry is pickled in binary format.

    snapShotDbObj:    Snapshot DB file (bsddb).

    key:              Key in DB (string).

    val:              Value to be put in the DB (<object>).

    sync:             Sync the DB to the DB file (integer/0|1).

    Returns:          Void.
    """
    T = TRACE(5)

    snapShotDbObj[key] = cPickle.dumps(val, 1)
    if (sync): snapShotDbObj.sync()


def _readDb(snapShotDbObj,
            key):
    """
    Read and unpickle a value referenced by its key from the file DB.

    snapShotDbObj:   Open DB object (bsddb).

    key:             Key to extract value from (string).

    Returns:         Void.
    """
    T = TRACE(5)

    return cPickle.loads(snapShotDbObj[key])


def _genFileKey(fileInfo):
    """
    Generate a dictionary key from information in the File Info object,
    which is either a list with information from ngas_files, or an
    ngamsFileInfo object.

    fileInfo:       File Info as read from the ngas_files table or
                    an instance of ngamsFileInfo (list|ngamsFileInfo).

    Returns:        File key (string).
    """
    T = TRACE(5)

    if ((type(fileInfo) == types.ListType) or
        (type(fileInfo) == types.TupleType)):
        fileId  = fileInfo[ngamsDbCore.NGAS_FILES_FILE_ID]
        fileVer = fileInfo[ngamsDbCore.NGAS_FILES_FILE_VER]
    else:
        fileId  = fileInfo.getFileId()
        fileVer = fileInfo.getFileVersion()
    return ngamsLib.genFileKey(None, fileId, fileVer)


##############################################################################
# DON'T CHANGE THESE IDs!!!
##############################################################################
NGAMS_SN_SH_ID2NM_TAG   = "___ID2NM___"
NGAMS_SN_SH_NM2ID_TAG   = "___NM2ID___"
NGAMS_SN_SH_MAP_COUNT   = "___MAP_COUNT___"
##############################################################################

def _encName(dbSnapshot,
             name):
    """
    Encode a name and add the name and its corresponding mapping ID (integer)
    in the file DB. The mapping is such that the name itself is referred to by

      NGAMS_SN_SH_ID2NM_TAG + ID -> <Name>

    The get from the name to the corresponding ID the following mapping
    should be used:

      NGAMS_SN_SH_NM2ID_TAG + <Name> -> <ID>

    dbSnapshot:      Open DB object (bsddb).

    name:            Name to be encoded (string).

    Returns:         The ID allocated to that name (integer).
    """
    T = TRACE(5)

    nm2IdTag = NGAMS_SN_SH_NM2ID_TAG + name
    if (dbSnapshot.has_key(nm2IdTag)):
        nameId = _readDb(dbSnapshot, nm2IdTag)
    else:
        if (dbSnapshot.has_key(NGAMS_SN_SH_MAP_COUNT)):
            count = (_readDb(dbSnapshot, NGAMS_SN_SH_MAP_COUNT) + 1)
        else:
            count = 0
        nameId = count
        id2NmTag = NGAMS_SN_SH_ID2NM_TAG + str(nameId)

        # Have to ensure that all three keys are entered in the DBM (this might
        # not be the right way, maybe there is something that can be done at
        # bsddb level.
        try:
            _addInDbm(dbSnapshot, NGAMS_SN_SH_MAP_COUNT, count)
        except Exception, e:
            _addInDbm(dbSnapshot, NGAMS_SN_SH_MAP_COUNT, count)
            _addInDbm(dbSnapshot, nm2IdTag, nameId)
            _addInDbm(dbSnapshot, id2NmTag, name, 1)
            raise e
        try:
            _addInDbm(dbSnapshot, nm2IdTag, nameId)
        except Exception, e:
            _addInDbm(dbSnapshot, NGAMS_SN_SH_MAP_COUNT, count)
            _addInDbm(dbSnapshot, nm2IdTag, nameId)
            _addInDbm(dbSnapshot, id2NmTag, name, 1)
            raise e
        _addInDbm(dbSnapshot, id2NmTag, name, 1)

    return nameId


def _unPickle(pickleObject):
    """
    Unpickle a pickled object.

    pickleObject:   Pickled object (<Pickle Data>).

    Returns:        Reference to unpickled object (<Object>).
    """
    T = TRACE(5)

    return cPickle.loads(pickleObject)


def _encFileInfo(dbConObj,
                 dbSnapshot,
                 fileInfo):
    """
    Encode the information about a file contained in a list as read
    from the DB and generate a dictionary with these values. The column
    names are encoded and mappings between the code (ID) and name are stored
    in the file DB.

    The elements in the list can be refferred to by the 'constants'

      ngamsDbCore.NGAS_FILES_DISK_ID ... ngamsDbCore.NGAS_FILES_CREATION_DATE


    dbConObj:        DB connection object (ngamsDb).

    dbSnapshot:    Open DB object (bsddb).

    fileInfo:      List with information about file from the DB (list).

    Returns:       Dictionary with encoded column names (dictionary).
    """
    T = TRACE(5)

    tmpDic = {}
    #for n in range(ngamsDbCore.NGAS_FILES_CREATION_DATE + 1):
    for n in range(ngamsDbCore.NGAS_FILES_IO_TIME + 1): #newly added column!
        colName = dbConObj.getNgasFilesMap()[n]
        colId = _encName(dbSnapshot, colName)
        tmpDic[colId] = fileInfo[n]
    return tmpDic


def _encFileInfo2Obj(dbConObj,
                     dbSnapshot,
                     encFileInfoDic):
    """
    Convert an encoded file info from the snapshot into an NG/AMS File
    Info Object.

    dbConObj:        DB connection object (ngamsDb).

    dbSnapshot:      Open DB object (bsddb).

    encFileInfoDic:  Dictionary containing the encoded file information
                     (dictionary).

    Returns:         NG/AMS File Info Object (ngamsFileInfo).
    """
    T = TRACE(5)

    sqlFileInfo = []
    #for n in range (ngamsDbCore.NGAS_FILES_CREATION_DATE + 1):
    for n in range (ngamsDbCore.NGAS_FILES_CONTAINER_ID + 1):
        sqlFileInfo.append(None)
    idxKeys = encFileInfoDic.keys()
    for idx in idxKeys:
        kid = NGAMS_SN_SH_ID2NM_TAG + str(idx)
        if (not dbSnapshot.has_key(kid)):
            warning("dbSnapshot has no key '{0}', is it corrupted?".format(kid))
            return None
        colName = _readDb(dbSnapshot, kid)
        sqlFileInfoIdx = dbConObj.getNgasFilesMap()[colName]
        sqlFileInfo[sqlFileInfoIdx] = encFileInfoDic[idx]
    tmpFileInfoObj = ngamsFileInfo.ngamsFileInfo().unpackSqlResult(sqlFileInfo)
    return tmpFileInfoObj


def _updateSnapshot(ngamsCfgObj):
    """
    Return 1 if the DB Snapshot should be updated, otherwise 0 is
    returned.

    ngamsCfgObj:   NG/AMS Configuration Object (ngamsConfig).

    Returns:       1 = update DB Snapshot, 0 = do not update DB Snapshot
                   (integer/0|1).
    """
    T = TRACE(5)

    if (ngamsCfgObj.getAllowArchiveReq() or ngamsCfgObj.getAllowRemoveReq()):
        return 1
    else:
        return 0


def _openDbSnapshot(ngamsCfgObj,
                    mtPt):
    """
    Open a bsddb file DB. If the file exists and this is not
    a read-only NGAS system the file is opened for reading and writing.
    If this is a read-only NGAS system it is only opened for reading.

    If the file DB does not exist, a new DB is created.

    If the file DB does not exist and this is a read-only NGAS system,
    None is returned.

    The name of the DB file is:

      <Disk Mount Point>/NGAMS_DB_DIR/NGAMS_DB_NGAS_FILES

    ngamsCfgObj:    NG/AMS Configuration Object (ngamsConfig).

    mtPt:           Mount point (string).

    Returns:        File DB object (bsddb|None).
    """
    T = TRACE()

    snapShotFile = os.path.normpath(mtPt + "/" + NGAMS_DB_DIR + "/" +\
                                    NGAMS_DB_NGAS_FILES)
    checkCreatePath(os.path.normpath(mtPt + "/" + NGAMS_DB_CH_CACHE))
    if (os.path.exists(snapShotFile)):
        if (_updateSnapshot(ngamsCfgObj)):
            # Open the existing DB Snapshot for reading and writing.
            snapshotDbm = bsddb.hashopen(snapShotFile, "w")
        else:
            # Open only for reading.
            snapshotDbm = bsddb.hashopen(snapShotFile, "r")
    else:
        if (_updateSnapshot(ngamsCfgObj)):
            # Create a new DB Snapshot.
            snapshotDbm = bsddb.hashopen(snapShotFile, "c")
        else:
            # There is no DB Snapshot and it is not possible to
            # create one - the check cannot be carried out.
            snapshotDbm = None

    # Remove possible, old /<mt pt>/.db/NgasFiles.xml snapshots.
    # TODO: Remove when it can be assumed that all old XML snapshots have
    #       been removed.
    rmFile(os.path.normpath(mtPt + "/" + NGAMS_DB_DIR + "/NgasFiles.xml"))

    return snapshotDbm


def _delFileEntry(hostId,
                  dbConObj,
                  fileInfoObj):
    """
    Delete a file entry in the NGAS DB. If the file does not exist,
    nothing is done. If the file exists, it will be deleted.

    dbConObj:        NG/AMS DB object (ngamsDB).

    fileInfoObj:     File Info Object (ngamsFileInfo).

    Returns:         Void.
    """
    T = TRACE(5)

    if (dbConObj.fileInDb(fileInfoObj.getDiskId(),
                          fileInfoObj.getFileId(),
                          fileInfoObj.getFileVersion())):
        try:
            dbConObj.deleteFileInfo(hostId,
                                    fileInfoObj.getDiskId(),
                                    fileInfoObj.getFileId(),
                                    fileInfoObj.getFileVersion(), 0)
        except:
            pass


def checkUpdateDbSnapShots(srvObj, stopEvt):
    """
    Check if a DB Snapshot exists for the DB connected. If not, this is
    created according to the contents of the NGAS DB (if possible). During
    this creation it is checked if the file are physically stored on the
    disk.

    srvObj:        Reference to NG/AMS server class object (ngamsServer).

    Returns:       Void.
    """
    T = TRACE()

    tmpSnapshotDbm = None
    lostFileRefsDbm = None
    snapshotDbm = None
    tmpSnapshotDbm = None

    if (not srvObj.getCfg().getDbSnapshot()):
        info(3,"NOTE: DB Snapshot Feature is switched off")
        return

    info(4,"Generate list of disks to check ...")
    tmpDiskIdMtPtList = srvObj.getDb().getDiskIdsMtPtsMountedDisks(srvObj.getHostId())
    diskIdMtPtList = []
    for diskId, mtPt in tmpDiskIdMtPtList:
        diskIdMtPtList.append([mtPt, diskId])
    diskIdMtPtList.sort()
    info(4,"Generated list of disks to check: " + str(diskIdMtPtList))

    # Generate temporary snapshot filename.
    ngasId = srvObj.getHostId()
    tmpDir = ngamsHighLevelLib.getTmpDir(srvObj.getCfg())

    # Temporary DBM with file info from the DB.
    tmpSnapshotDbmName = os.path.normpath(tmpDir + "/" + ngasId + "_" +\
                                          NGAMS_DB_NGAS_FILES)

    # Temporary DBM to contain information about 'lost files', i.e. files,
    # which are registered in the DB and found in the DB Snapshot, but
    # which are not found on the disk.
    info(4,"Create DBM to hold information about lost files ...")
    lostFileRefsDbmName = os.path.normpath(tmpDir + "/" + ngasId +\
                                           "_LOST_FILES")
    rmFile(lostFileRefsDbmName + "*")
    lostFileRefsDbm = ngamsDbm.ngamsDbm(lostFileRefsDbmName, writePerm=1)
    info(4,"Created DBM to hold information about lost files")

    # Carry out the check.
    for mtPt, diskId in diskIdMtPtList:

        checkStopJanitorThread(stopEvt)

        info(2,"Check/create/update DB Snapshot for disk with " +\
             "mount point: " + mtPt)

        try:
            snapshotDbm = _openDbSnapshot(srvObj.getCfg(), mtPt)
            if (snapshotDbm == None):
                continue

            # The scheme for synchronizing the Snapshot and the DB is:
            #
            # - Loop over file entries in the Snapshot:
            #  - If in DB:
            #    - If file on disk     -> OK, do nothing.
            #    - If file not on disk -> Accumulate + issue collective warning.
            #
            #  - If entry not in DB:
            #    - If file on disk     -> Add entry in DB.
            #    - If file not on disk -> Remove entry from Snapshot.
            #
            # - Loop over entries for that disk in the DB:
            #  - If entry in Snapshot  -> OK, do nothing.
            #  - If entry not in Snapshot:
            #    - If file on disk     -> Add entry in Snapshot.
            #    - If file not on disk -> Remove entry from DB.

            # Create a temporary DB Snapshot with the files from the DB.
            #
            # TODO: This algorithm could be improved such that the intermediate
            #       DBM (tmpSnapshotDbm) is not created. I.e., tmpFileListDbm
            #       is used diretly futher down.
            tmpFileListDbm = None
            tmpFileListDbmName = None
            try:
                rmFile(tmpSnapshotDbmName + "*")
                tmpSnapshotDbm = bsddb.hashopen(tmpSnapshotDbmName, "c")
                tmpFileListDbmName = srvObj.getDb().dumpFileInfoList(diskId,
                                                                     ignore=None)
                tmpFileListDbm = ngamsDbm.ngamsDbm(tmpFileListDbmName)
                while (1):
                    key, fileInfo = tmpFileListDbm.getNext()
                    if (not key): break
                    fileKey = _genFileKey(fileInfo)
                    encFileInfoDic = _encFileInfo(srvObj.getDb(), tmpSnapshotDbm,
                                                  fileInfo)
                    _addInDbm(tmpSnapshotDbm, fileKey, encFileInfoDic)
                    checkStopJanitorThread(stopEvt)
                    time.sleep(0.005)
                tmpSnapshotDbm.sync()
            finally:
                rmFile(tmpSnapshotDbmName)
                if tmpFileListDbmName:
                    rmFile(tmpFileListDbmName)
                if tmpFileListDbm:
                    del tmpFileListDbm
            #####################################################################
            # Loop over the possible entries in the DB Snapshot and compare
            # these against the DB.
            #####################################################################
            info(4,"Loop over file entries in the DB Snapshot - %s ..." % diskId)
            count = 0
            try:
                key, pickleValue = snapshotDbm.first()
            except Exception, e:
                msg = "Exception raised accessing DB Snapshot for disk: %s. " +\
                      "Error: %s"
                info(4,msg % (diskId, str(e)))
                key = None
                snapshotDbm.dbc = None

            # Create a DBM which is used to keep the list of files to remove
            # from the DB Snapshot.
            snapshotDelDbmName = ngamsHighLevelLib.\
                                 genTmpFilename(srvObj.getCfg(),
                                                NGAMS_DB_NGAS_FILES)
            snapshotDelDbm = ngamsDbm.ngamsDbm(snapshotDelDbmName,
                                               cleanUpOnDestr=1,
                                               writePerm=1)

            #################################################################################################
            #jagonzal: Replace looping aproach to avoid exceptions coming from the next() method underneath
            #          when iterating at the end of the table that are prone to corrupt the hash table object
            #while (key):
            for key,pickleValue in snapshotDbm.iteritems():
            #################################################################################################
                value = _unPickle(pickleValue)

                # Check if an administrative element, if yes add it if necessary.
                if (key.find("___") != -1):
                    if (not tmpSnapshotDbm.has_key(key)):
                        tmpSnapshotDbm[key] = pickleValue
                else:
                    tmpFileObj = _encFileInfo2Obj(srvObj.getDb(), snapshotDbm,
                                                  value)
                    if (tmpFileObj is None):
                        continue
                    complFilename = os.path.normpath(mtPt + "/" +\
                                                     tmpFileObj.getFilename())

                    # Is the file in the DB?
                    if (tmpSnapshotDbm.has_key(key)):
                        # Is the file on the disk?
                        if (not os.path.exists(complFilename)):
                            fileVer = tmpFileObj.getFileVersion()
                            tmpFileObj.setTag(complFilename)
                            fileKey = ngamsLib.genFileKey(tmpFileObj.getDiskId(),
                                                          tmpFileObj.getFileId(),
                                                          fileVer)
                            lostFileRefsDbm.add(fileKey, tmpFileObj)
                            lostFileRefsDbm.sync()
                    elif (not tmpSnapshotDbm.has_key(key)):
                        tmpFileObj = _encFileInfo2Obj(srvObj.getDb(), snapshotDbm,
                                                      value)
                        if (tmpFileObj is None):
                            continue

                        # Is the file on the disk?
                        if (os.path.exists(complFilename)):
                            # Add this entry in the NGAS DB.
                            tmpFileObj.write(srvObj.getHostId(), srvObj.getDb(), 0, 1)
                            tmpSnapshotDbm[key] = pickleValue
                        else:
                            # Remove this entry from the DB Snapshot.
                            if (getMaxLogLevel() >= 5):
                                msg = "Scheduling entry: %s in DB Snapshot " +\
                                      "for disk with ID: %s for removal"
                                info(4,msg % (diskId, key))
                            # Add entry in the DB Snapshot Deletion DBM marking
                            # the entry for deletion.
                            if (_updateSnapshot(srvObj.getCfg())):
                                snapshotDelDbm.add(key, 1)

                        del tmpFileObj

                # Be friendly, make a break every now and then + sync the DB file.
                count += 1
                if ((count % 100) == 0):
                    if (_updateSnapshot(srvObj.getCfg())): snapshotDbm.sync()
                    checkStopJanitorThread(stopEvt)
                    tmpSnapshotDbm.sync()
                    time.sleep(0.010)
                else:
                    time.sleep(0.002)
                #################################################################################################
                #jagonzal: Replace looping aproach to avoid exceptions coming from the next() method underneath
                #          when iterating at the end of the table that are prone to corrupt the hash table object
                #try:
                #    key, pickleValue = snapshotDbm.next()
                #except:
                #    key = None
                #    snapshotDbm.dbc = None
                #################################################################################################

            # Now, delete entries in the DB Snapshot if there are any scheduled for
            # deletion.

            #################################################################################################
            #jagonzal: Replace looping aproach to avoid exceptions coming from the next() method underneath
            #          when iterating at the end of the table that are prone to corrupt the hash table object
            #snapshotDelDbm.initKeyPtr()
            #while (True):
            #    key, value = snapshotDelDbm.getNext()
            #    if (not key): break
            for key,value in snapshotDelDbm.iteritems():
                # jagonzal: We need to reformat the values and skip administrative elements #################
                if (str(key).find("__") != -1): continue
                #############################################################################################
                if (getMaxLogLevel() >= 4):
                    msg = "Removing entry: %s from DB Snapshot for " +\
                          "disk with ID: %s"
                    info(4,msg % (key, diskId))
                del snapshotDbm[key]
            #################################################################################################
            del snapshotDelDbm

            info(4,"Looped over file entries in the DB Snapshot - %s" % diskId)
            # End-Loop: Check DB against DB Snapshot. ###########################
            if (_updateSnapshot(srvObj.getCfg())): snapshotDbm.sync()
            tmpSnapshotDbm.sync()

            info(2,"Checked/created/updated DB Snapshot for disk with " +\
                 "mount point: " + mtPt)

            #####################################################################
            # Loop over the entries in the DB and compare these against the
            # DB Snapshot.
            #####################################################################
            info(4,"Loop over the entries in the DB - %s ..." % diskId)
            count = 0
            try:
                key, pickleValue = tmpSnapshotDbm.first()
            except Exception, e:
                key = None
                tmpSnapshotDbm.dbc = None

            #################################################################################################
            #jagonzal: Replace looping aproach to avoid exceptions coming from the next() method underneath
            #          when iterating at the end of the table that are prone to corrupt the hash table object
            #while (key):
            for key,pickleValue in tmpSnapshotDbm.iteritems():
            #################################################################################################
                value = _unPickle(pickleValue)

                # Check if it is an administrative element, if yes add it if needed
                if (key.find("___") != -1):
                    if (not snapshotDbm.has_key(key)):
                        snapshotDbm[key] = pickleValue
                else:
                    # Is the file in the DB Snapshot?
                    if (not snapshotDbm.has_key(key)):
                        tmpFileObj = _encFileInfo2Obj(srvObj.getDb(),
                                                      tmpSnapshotDbm, value)
                        if (tmpFileObj is None):
                            continue

                        # Is the file on the disk?
                        complFilename = os.path.normpath(mtPt + "/" +\
                                                         tmpFileObj.getFilename())
                        if (os.path.exists(complFilename)):
                            # Add this entry in the DB Snapshot.
                            if (_updateSnapshot(srvObj.getCfg())):
                                snapshotDbm[key] = pickleValue
                        else:
                            # Remove this entry from the DB (if it is there).
                            _delFileEntry(srvObj.getHostId(), srvObj.getDb(), tmpFileObj)
                        del tmpFileObj
                    else:
                        # We always update the DB Snapshot to ensure it is
                        # in-sync with the DB entry.
                        if (_updateSnapshot(srvObj.getCfg())):
                            snapshotDbm[key] = pickleValue

                # Be friendly and make a break every now and then +
                # sync the DB file.
                count += 1
                if ((count % 100) == 0):
                    if (_updateSnapshot(srvObj.getCfg())): snapshotDbm.sync()
                    checkStopJanitorThread(stopEvt)
                    time.sleep(0.010)
                else:
                    time.sleep(0.002)
                #################################################################################################
                #jagonzal: Replace looping aproach to avoid exceptions coming from the next() method underneath
                #          when iterating at the end of the table that are prone to corrupt the hash table object
                #try:
                #    key, pickleValue = tmpSnapshotDbm.next()
                #except:
                #    key = None
                #################################################################################################
            info(4,"Checked DB Snapshot against DB - %s" % diskId)
            # End-Loop: Check DB Snapshot against DB. ###########################
            if (_updateSnapshot(srvObj.getCfg())):
                snapshotDbm.sync()

        finally:
            if snapshotDbm:
                snapshotDbm.close()

            if tmpSnapshotDbm:
                tmpSnapshotDbm.close()

    # Check if lost files found.
    info(4,"Check if there are Lost Files ...")
    noOfLostFiles = lostFileRefsDbm.getCount()
    if (noOfLostFiles):
        statRep = os.path.normpath(tmpDir + "/" + ngasId +\
                                   "_LOST_FILES_NOTIF_EMAIL.txt")
        fo = open(statRep, "w")
        timeStamp = PccUtTime.TimeStamp().getTimeStamp()
        tmpFormat = "JANITOR THREAD - LOST FILES DETECTED:\n\n" +\
                    "==Summary:\n\n" +\
                    "Date:                       %s\n" +\
                    "NGAS Host ID:               %s\n" +\
                    "Lost Files:                 %d\n\n" +\
                    "==File List:\n\n"
        fo.write(tmpFormat % (timeStamp, srvObj.getHostId(), noOfLostFiles))

        tmpFormat = "%-32s %-32s %-12s %-80s\n"
        fo.write(tmpFormat % ("Disk ID", "File ID", "File Version",
                              "Expected Path"))
        fo.write(tmpFormat % (32 * "-", 32 * "-", 12 * "-", 80 * "-"))

        # Loop over the files an generate the report.
        lostFileRefsDbm.initKeyPtr()
        while (1):
            key, fileInfoObj = lostFileRefsDbm.getNext()
            if (not key): break
            diskId      = fileInfoObj.getDiskId()
            fileId      = fileInfoObj.getFileId()
            fileVersion = fileInfoObj.getFileVersion()
            filename    = fileInfoObj.getTag()
            fo.write(tmpFormat % (diskId, fileId, fileVersion, filename))
        fo.write("\n\n==END\n")
        fo.close()
        ngamsNotification.notify(srvObj.getHostId(), srvObj.getCfg(), NGAMS_NOTIF_DATA_CHECK,
                                 "LOST FILE(S) DETECTED", statRep,
                                 [], 1, NGAMS_TEXT_MT,
                                 NGAMS_JANITOR_THR + "_LOST_FILES", 1)
        rmFile(statRep)
    info(4,"Checked if there are Lost Files. Number of lost files: %d" %\
         noOfLostFiles)

    # Clean up.
    del lostFileRefsDbm
    rmFile(lostFileRefsDbmName + "*")


def checkDbChangeCache(srvObj,
                       diskId,
                       diskMtPt,
                       stopEvt):
    """
    The function merges the information in the DB Change Snapshot Documents
    in the DB cache area on the disk concerned, into the Main DB Snapshot
    Document in a safe way which prevents that any information is lost.

    srvObj:        Reference to NG/AMS server class object (ngamsServer).

    diskId:        ID for disk (string).

    diskMtPt:      Mount point of the disk, e.g. '/NGAS/disk1' (string).

    Returns:       Void.
    """
    T = TRACE(5)

    if (not srvObj.getCfg().getDbSnapshot()): return
    if (not _updateSnapshot(srvObj.getCfg())): return

    snapshotDbm = None
    try:
        snapshotDbm = _openDbSnapshot(srvObj.getCfg(), diskMtPt)
        if (snapshotDbm == None):
            return

        # Remove possible, old /<mt pt>/.db/cache/*.xml snapshots.
        # TODO: Remove when it can be assumed that all old XML snapshots have
        #       been removed.
        rmFile(os.path.normpath(diskMtPt + "/" + NGAMS_DB_CH_CACHE + "/*.xml"))

        # Update the Status document with the possibly new entries.
        # TODO: Potential memory bottleneck. Use 'find > file' as for
        #       REGISTER Command.
        dbCacheFilePat = os.path.normpath("%s/%s/*.%s" %\
                                          (diskMtPt, NGAMS_DB_CH_CACHE,
                                           NGAMS_PICKLE_FILE_EXT))
        tmpCacheFiles = glob.glob(dbCacheFilePat)
        tmpCacheFiles.sort()
        cacheStatObj = None
        count = 0
        fileCount = 0
        noOfCacheFiles = len(tmpCacheFiles)
        timer = PccUtTime.Timer()
        for cacheFile in tmpCacheFiles:
            checkStopJanitorThread(stopEvt)
            if os.lstat(cacheFile)[6] == 0:
                os.remove(cacheFile)    # sometimes there are pickle files with 0 size.
                                        # we don't want to stop on them
                continue

            cacheStatObj = ngamsLib.loadObjPickleFile(cacheFile)
            if (isinstance(cacheStatObj, types.ListType)):
                # A list type in the Temporary DB Snapshot means that the
                # file has been removed.
                cacheStatList = cacheStatObj
                tmpFileInfoObjList = [ngamsFileInfo.ngamsFileInfo().\
                                      setDiskId(cacheStatList[0]).\
                                      setFileId(cacheStatList[1]).\
                                      setFileVersion(cacheStatList[2])]
                operation = NGAMS_DB_CH_FILE_DELETE
            elif (isinstance(cacheStatObj, ngamsFileInfo.ngamsFileInfo)):
                tmpFileInfoObjList = [cacheStatObj]
                operation = cacheStatObj.getTag()
            else:
                # Assume a ngamsFileList object.
                cacheFileListObj = cacheStatObj.getFileListList()[0]
                tmpFileInfoObjList = cacheFileListObj.getFileInfoObjList()
                operation = cacheFileListObj.getComment()

            # Loop over the files in the temporary snapshot.
            for tmpFileInfoObj in tmpFileInfoObjList:
                fileKey = _genFileKey(tmpFileInfoObj)
                fileInfoList = tmpFileInfoObj.genSqlResult()
                encFileInfoDic = _encFileInfo(srvObj.getDb(), snapshotDbm,
                                              fileInfoList)
                if ((operation == NGAMS_DB_CH_FILE_INSERT) or
                    (operation == NGAMS_DB_CH_FILE_UPDATE)):
                    _addInDbm(snapshotDbm, fileKey, encFileInfoDic)
                    tmpFileInfoObj.write(srvObj.getHostId(), srvObj.getDb(), 0)
                elif (operation == NGAMS_DB_CH_FILE_DELETE):
                    if (snapshotDbm.has_key(fileKey)): del snapshotDbm[fileKey]
                    _delFileEntry(srvObj.getHostId(), srvObj.getDb(), tmpFileInfoObj)
                else:
                    # Should not happen.
                    pass
            del cacheStatObj

            # Sleep if not last iteration (or if only one file).
            fileCount += 1
            if (fileCount < noOfCacheFiles): time.sleep(0.010)

            # Synchronize the DB.
            count += 1
            if (count == 100):
                snapshotDbm.sync()
                checkStopJanitorThread(stopEvt)
                count = 0

        # Clean up, delete the temporary File Remove Status Document.
        snapshotDbm.sync()

        for cacheFile in tmpCacheFiles:
            rmFile(cacheFile)
        totTime = timer.stop()

        tmpMsg = "Handled DB Snapshot Cache Files. Mount point: %s. " +\
                 "Number of Cache Files handled: %d."
        tmpMsg = tmpMsg % (diskMtPt, fileCount)
        if (fileCount):
            tmpMsg += "Total time: %.3fs. Time per file: %.3fs." %\
                      (totTime, (totTime / fileCount))
        info(4, tmpMsg)
    finally:
        if snapshotDbm:
            snapshotDbm.close()



def updateDbSnapShots(srvObj,
                      stopEvt,
                      diskInfo = None):
    """
    Check/update the DB Snapshot Documents for all disks.

    srvObj:            Reference to NG/AMS server class object (ngamsServer).

    diskInfo:          If a Snapshot should only be updated for a specific
                       disk, this can be specifically indicated by giving
                       the Disk ID and Mount Point of the disk (list).

    Returns:           Void.
    """
    T = TRACE()

    if (diskInfo):
        diskId = diskInfo[0]
        mtPt = diskInfo[1]
        if (diskId and mtPt):
            mtPt = diskInfo[1]
        else:
            mtPt = srvObj.getDb().getMtPtFromDiskId(diskId)
        if (not mtPt):
            notice("No mount point returned for Disk ID: %s" % diskId)
            return
        try:
            checkDbChangeCache(srvObj, diskId, mtPt, stopEvt)
        except Exception, e:
            msg = "Error checking DB Change Cache for " +\
                  "Disk ID:mountpoint: %s:%s. Error: %s"
            msg = msg % (diskId, str(mtPt), str(e))
            error(msg)
            raise Exception, msg
    else:
        tmpDiskIdMtPtList = srvObj.getDb().\
                            getDiskIdsMtPtsMountedDisks(srvObj.getHostId())
        diskIdMtPtList = []
        for diskId, mtPt in tmpDiskIdMtPtList:
            diskIdMtPtList.append([mtPt, diskId])
        diskIdMtPtList.sort()
        for mtPt, diskId in diskIdMtPtList:
            info(4,"Check/Update DB Snapshot Document for disk with " +\
                 "mount point: " + mtPt)
            try:
                checkDbChangeCache(srvObj, diskId, mtPt, stopEvt)
            except Exception, e:
                msg = "Error checking DB Change Cache for " +\
                      "Disk ID:mountpoint: %s:%s. Error: %s"
                msg = msg % (diskId, str(mtPt), str(e))
                error(msg)
                raise Exception, msg

def JanitorCycle(srvObj, stopEvt, suspendTime, JanQue):
    """


    srvObj:      Reference to server object (ngamsServer).

    dummy:       Needed by the thread handling ...

    Returns:     Void.
    """
    #import multiprocessing


    #pool=multiprocessing.Pool(processes=2,maxtasksperchild=1)


    try:
        checkStopJanitorThread(stopEvt)
        info(4, "Janitor Thread running-Janitor Cycle.. ")
        print('Inside Janitor cycle proc id is ', os.getpid())

        # jobs=[] #a list we may use to keep track of jobs forked from main process
        #
        # ##################################################################
        # # => Check if there are any Temporary DB Snapshot Files to handle.
        # ##################################################################
        from ngamsPlugIns import ngamsJanitorHandleTempDBSnapshotFiles
        ngamsJanitorHandleTempDBSnapshotFiles.Handle_TempDB_SnapShot_Files(srvObj, stopEvt, updateDbSnapShots)
        # from ngamsPlugIns import ngamsJanitorHandleTempDBSnapshotFiles
        #
        # pool.proc1 = multiprocessing.Process(target=ngamsJanitorHandleTempDBSnapshotFiles.Handle_TempDB_SnapShot_Files, args=(srvObj, stopEvt, updateDbSnapShots))
        # jobs.append(pool.proc1)
        # pool.proc1.start()
        # ##################################################################
        # # => Check if we need to clean up Processing Directory (if
        # #    appropriate). If a Processing Directory is more than
        # #    30 minutes old, it is deleted.
        # ##################################################################
        from ngamsPlugIns import ngamsJanitorCheckProcessingDirectory
        ngamsJanitorCheckProcessingDirectory.Check_Processing_Directory(srvObj, stopEvt, checkCleanDirs)
        # from ngamsPlugIns import ngamsJanitorCheckProcessingDirectory
        #
        # pool.proc2 = multiprocessing.Process(target=ngamsJanitorCheckProcessingDirectory.Check_Processing_Directory, args=(srvObj, stopEvt, checkCleanDirs))
        # jobs.append(pool.proc2)
        # pool.proc2.start()
        #
        # ##################################################################
        # # => Check if there are old Requests in the Request DBM, which
        # #    should be removed.
        # ##################################################################
        from ngamsPlugIns import ngamsJanitorCheckOldRequestsinDBM
        ngamsJanitorCheckOldRequestsinDBM.Check_Old_RequestsinDBM(srvObj, stopEvt, checkStopJanitorThread)
        # from ngamsPlugIns import ngamsJanitorCheckOldRequestsinDBM
        #
        # pool.proc3 = multiprocessing.Process(target=ngamsJanitorCheckOldRequestsinDBM.Check_Old_RequestsinDBM, args=(srvObj, stopEvt, checkStopJanitorThread))
        # jobs.append(pool.proc3)
        # pool.proc3.start()
        #
        # ##################################################################
        # # => Check if we need to clean up Subscription Back-Log Buffer.
        # #     and check if there are left-over files in the NG/AMS Temp. Dir.
        # ##################################################################
        from ngamsPlugIns import ngamsJanitorCheckSubscrBacklognTempDir
        ngamsJanitorCheckSubscrBacklognTempDir.Check_Subscr_Backlog_n_Temp_Dir(srvObj, stopEvt, checkCleanDirs)
        # from ngamsPlugIns import ngamsJanitorCheckSubscrBacklognTempDir
        #
        # pool.proc4 = multiprocessing.Process(target=ngamsJanitorCheckSubscrBacklognTempDir.Check_Subscr_Backlog_n_Temp_Dir, args=(srvObj, stopEvt, checkCleanDirs))
        # jobs.append(pool.proc4)
        # pool.proc4.start()
        #
        # => Check for retained Email Notification Messages to send out.
        ngamsNotification.checkNotifRetBuf(srvObj.getHostId(), srvObj.getCfg())
        #
        # ##################################################################
        # # => Check LOG-file rotation and clean-up.
        # ##################################################################
        #
        # => Check there are any unsaved log files from a shutdown and archive them.
        from ngamsPlugIns import ngamsJanitorCheckUnsavedLogFile
        ngamsJanitorCheckUnsavedLogFile.CheckUnsavedLogFile(srvObj, stopEvt)
        # from ngamsPlugIns import ngamsJanitorCheckUnsavedLogFile
        #
        # pool.proc5 = multiprocessing.Process(target=ngamsJanitorCheckUnsavedLogFile.CheckUnsavedLogFile, args=(srvObj, stopEvt))
        # jobs.append(pool.proc5)
        # pool.proc5.start()
        # => Check if its time to carry out a rotation of the log file.
        from ngamsPlugIns import ngamsJanitorLogRotChk
        ngamsJanitorLogRotChk.Log_Rot_Chk(srvObj, stopEvt)
        # from ngamsPlugIns import ngamsJanitorLogRotChk
        #
        # pool.proc6 = multiprocessing.Process(target=ngamsJanitorLogRotChk.Log_Rot_Chk, args=(srvObj, stopEvt))
        # jobs.append(pool.proc6)
        # pool.proc6.start()
        #
        # ##################################################################
        # # => Check if there are rotated Local Log Files to remove.
        # ##################################################################
        from ngamsPlugIns import ngamsJanitorRotatedLogFilestoRemove
        ngamsJanitorRotatedLogFilestoRemove.Rotated_Log_FilestoRemove(srvObj, stopEvt)
        # from ngamsPlugIns import ngamsJanitorRotatedLogFilestoRemove
        #
        # pool.proc7 = multiprocessing.Process(target=ngamsJanitorRotatedLogFilestoRemove.Rotated_Log_FilestoRemove, args=(srvObj, stopEvt))
        # jobs.append(pool.proc7)
        # pool.proc7.start()
        #
        # ##################################################################
        # # => Check if there is enough disk space for the various
        # #    directories defined.
        # ##################################################################
        from ngamsPlugIns import ngamsJanitorCheckDiskSpace
        ngamsJanitorCheckDiskSpace.Check_Disk_Space(srvObj, stopEvt)
        # from ngamsPlugIns import ngamsJanitorCheckDiskSpace
        #
        # pool.proc8 = multiprocessing.Process(target=ngamsJanitorCheckDiskSpace.Check_Disk_Space, args=(srvObj, stopEvt))
        # jobs.append(pool.proc8)
        # pool.proc8.start()
        #
        # ##################################################################
        # # => Check if this NG/AMS Server is requested to wake up
        # #    another/other NGAS Host(s).
        # ##################################################################
        from ngamsPlugIns import ngamsJanitorChecktoWakeupOtherNGASHost
        ngamsJanitorChecktoWakeupOtherNGASHost.Check_to_Wakeup_OtherNGAS_Host(srvObj, stopEvt)
        # from ngamsPlugIns import ngamsJanitorChecktoWakeupOtherNGASHost
        #
        # pool.proc9 = multiprocessing.Process(target=ngamsJanitorChecktoWakeupOtherNGASHost.Check_to_Wakeup_OtherNGAS_Host, args=(srvObj, stopEvt))
        # jobs.append(pool.proc9)
        # pool.proc9.start()
        #
        # ##################################################################
        # # => Check if the conditions for suspending this NGAS Host are met.
        # ##################################################################
        from ngamsPlugIns import ngamsJanitorChecktoSuspendNGASHost
        ngamsJanitorChecktoSuspendNGASHost.Check_to_Suspend_NGAS_Host(srvObj, stopEvt)
        # from ngamsPlugIns import ngamsJanitorChecktoSuspendNGASHost
        #
        # pool.proc10 = multiprocessing.Process(target=ngamsJanitorChecktoSuspendNGASHost.Check_to_Suspend_NGAS_Host, args=(srvObj, stopEvt))
        # jobs.append(pool.proc10)
        # pool.proc10.start()
        #

        #
        # pool.close()
        # pool.join()

        # Suspend the thread for the time indicated.
        # Update the Janitor Thread run count.
        srvObj.incJanitorThreadRunCount()
        JanQue.put(srvObj.getJanitorThreadRunCount())
        print("==============================Thread count in Jan is ", srvObj.getJanitorThreadRunCount())

        # Suspend the thread for the time indicated.
        info(4, "Janitor Thread executed - suspending for %d [s] ..." % (suspendTime,))
        startTime = time.time()
        event_info_list = JanQue.get()  #==================================================
        while ((time.time() - startTime) < suspendTime):
            # Check if we should update the DB Snapshot.
            if (event_info_list):
                time.sleep(0.5)
                try:
                    diskInfo = None
                    if (event_info_list):
                        for diskInfo in event_info_list:
                            updateDbSnapShots(srvObj, stopEvt, diskInfo)
                except Exception, e:
                    if (diskInfo):
                        msg = "Error encountered handling DB Snapshot " + \
                              "for disk: %s/%s. Exception: %s"
                        msg = msg % (diskInfo[0], diskInfo[1], str(e))
                    else:
                        msg = "Error encountered handling DB Snapshot. " + \
                              "Exception: %s" % str(e)
                    error(msg)
                    time.sleep(5)
            suspend(stopEvt, 1.0)

    except StopJanitorThreadException:
        raise
    except Exception, e:
        errMsg = "Error occurred during execution of the Janitor " + \
                 "Thread. Exception: " + str(e)
        alert(errMsg)
        # We make a small wait here to avoid that the process tries
        # too often to carry out the tasks that failed.
        time.sleep(2.0)


def janitorThread(srvObj, stopEvt, JanQue):    #dbChangeSync = ngamsEvent.ngamsEvent()
    """
    The Janitor Thread runs periodically when the NG/AMS Server is
    Online to 'clean up' the NG/AMS environment. Task performed are
    checking if any data is available in the Back-Log Buffer, and
    archiving of these in case yes, checking if there are any Processing
    Directories to be deleted.

    srvObj:      Reference to server object (ngamsServer).

    dummy:       Needed by the thread handling ...

    Returns:     Void.
    """
    T = TRACE()

    # Make the event object to synchronize DB Snapshot updates available
    # for the ngamsDb class.


    #janitordbChangeSync= ngamsEvent.ngamsEvent()
    #srvObj.getDb().addDbChangeEvt(dbChangeSync)
    info(4, "=====Janitor Thread ===== into it ...")
    print("============================================Janitor Thread ===== into it ...")

    hostId = srvObj.getHostId()

    # => Update NGAS DB + DB Snapshot Document for the DB connected.
    try:
        checkUpdateDbSnapShots(srvObj, stopEvt)
    except StopJanitorThreadException:
        return
    except Exception, e:
        errMsg = "Problem updating DB Snapshot files: " + str(e)
        warning(errMsg)
        import traceback
        info(3, traceback.format_exc())

    suspendTime = isoTime2Secs(srvObj.getCfg().getJanitorSuspensionTime())
    #==========================================================
    #=== Move contents of while loop to JanitorCycle method
    #===========================================================

    try:
        while True:
            # Incapsulate this whole block to avoid that the thread dies in
            # case a problem occurs, like e.g. a problem with the DB connection.
            #

            JanitorCycle(srvObj, stopEvt, suspendTime, JanQue)
            # Update the Janitor Thread run count.
            #srvObj.incJanitorThreadRunCount()
            #JanQue.put(srvObj.getJanitorThreadRunCount())
            #print("==============================Thread count in Jan is ",srvObj.getJanitorThreadRunCount())

            # pool.proc1 = multiprocessing.Process(target=JanitorCycle, args=(srvObj, stopEvt, suspendTime, dbChangeSync))
            # pool.proc1.start()
            #
            # pool.close()
            # pool.join()
    except StopJanitorThreadException:
        return


# EOF
