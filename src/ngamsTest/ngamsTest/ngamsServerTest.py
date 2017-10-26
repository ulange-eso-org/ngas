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
# "@(#) $Id: ngamsServerTest.py,v 1.4 2008/08/19 20:51:50 jknudstr Exp $"
#
# Who       When        What
# --------  ----------  -------------------------------------------------------
# jknudstr  18/11/2003  Created
#
"""
This module contains the Test Suite for the NG/AMS Server.
"""

import contextlib
import os
import socket
import subprocess
import sys
import threading
import time

from ngamsLib import ngamsHttpUtils
from ngamsLib.ngamsCore import NGAMS_SUCCESS, NGAMS_HTTP_SERVICE_NA
from ngamsTestLib import ngamsTestSuite, runTest, saveInFile, sendPclCmd, this_dir


class ngamsServerTest(ngamsTestSuite):

    def test_slow_receiving_client(self):
        """
        This test checks that the NGAS server doesn't hang forever on a slow
        client, since it would block the server for ever
        """

        timeout = 3
        amount_of_data = 10*1024*1024 # 10 MBs
        spaces = " " * amount_of_data
        self.prepExtSrv(cfgProps=[["NgamsCfg.Server[1].TimeOut",str(timeout)]])

        client = sendPclCmd()
        status = client.archive_data(spaces, 'some-file.data', 'application/octet-stream')
        self.assertEquals(NGAMS_SUCCESS, status.getStatus())

        # Normal retrieval works fine
        self.assertEquals(NGAMS_SUCCESS, client.retrieve(fileId='some-file.data').getStatus())
        os.unlink('some-file.data')

        # Now retrieve the data, but sloooooooooooowly and check that the server
        # times out and closes the connection, which in turn makes our receiving
        # end finish earlier than expected. This is detected on the client side
        # because we receive less data than we ask for).
        #
        # We have to make sure that the receiving buffer is tiny so the server
        # really can't write any more data into the socket. In the same spirit
        # we specify a very small send buffer for the server. We don't need to
        # specify a timeout because the recv will return immediately if the
        # server has closed the connection.
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256)
        s.connect(('localhost', 8888))
        s.send('GET /RETRIEVE?file_id=some-file.data&send_buffer=1024 HTTP/1.0\r\n')
        s.send('\r\n')
        time.sleep(timeout + 2) # More than enough to provoke a server timeout

        data = s.recv(amount_of_data, socket.MSG_WAITALL)
        self.assertLess(len(data), amount_of_data, "Should have read less data")
        self.assertEquals('', s.recv(amount_of_data - len(data)))
        s.close()

    def test_too_many_requests(self):

        saveInFile("tmp/handleHttpRequest_tmp", "handleHttpRequest_Block5secs")
        self.prepExtSrv(srvModule="ngamsSrvTestDynReqCallBack",
                        cfgProps=(('NgamsCfg.Server[1].MaxSimReqs', '2'),))

        # Fire off two clients, each takes 5 seconds to finish
        cl1, cl2 =  sendPclCmd(), sendPclCmd()
        threading.Thread(target=cl1.online).start()
        threading.Thread(target=cl2.online).start()

        # The third one should not pass through
        # (assuming that 2 seconds were enough for the two clients
        # to connect and be busy waiting for their reply)
        time.sleep(2)
        resp = ngamsHttpUtils.httpGet('127.0.0.1', 8888, 'ONLINE')
        with contextlib.closing(resp):
            self.assertEqual(NGAMS_HTTP_SERVICE_NA, resp.status)

class ngamsDaemonTest(ngamsTestSuite):

    def _run_daemon_status(self, cfg_file):
        execCmd  = [sys.executable, '-m', 'ngamsServer.ngamsDaemon', 'status']
        execCmd += ['-cfg', cfg_file]
        with self._proc_startup_lock:
            daemon_status_proc = subprocess.Popen(execCmd, shell=False)
        return daemon_status_proc.wait()

    def test_start_via_daemon(self):
        self.prepExtSrv(daemon=True)

    def test_daemon_status(self):
        self.prepExtSrv(daemon=True)
        self.assertEquals(0, self._run_daemon_status(self.extSrvInfo[-1].cfg_file))

    def test_daemon_status_no_server_running(self):
        self.assertEquals(1, self._run_daemon_status(os.path.join(this_dir, 'src/ngamsCfg.xml')))

    def test_daemon_double_start(self):
        # Try to start the daemon in the same port, should fail
        self.prepExtSrv(daemon=True)
        self.assertRaises(Exception, self.prepExtSrv, delDirs=False, clearDb=False, daemon=True)

def run():
    """
    Run the complete test.

    Returns:   Void.
    """
    runTest(["ngamsServerTest"])


if __name__ == '__main__':
    """
    Main program executing the test cases of the module test.
    """
    runTest(sys.argv)


# EOF
