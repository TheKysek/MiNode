# -*- coding: utf-8 -*-
import logging
import socket
import threading

import shared
from connection import Connection
from i2p.util import receive_line


class I2PDialer(threading.Thread):
    def __init__(self, destination, nick, sam_host='127.0.0.1', sam_port=7656):
        self.sam_host = sam_host
        self.sam_port = sam_port

        self.nick = nick
        self.destination = destination

        super().__init__(name='I2P Dial to {}'.format(self.destination))

        self.s = socket.create_connection((self.sam_host, self.sam_port))

        self.version_reply = []
        self.success = True

    def run(self):
        logging.debug('Connecting to {}'.format(self.destination))
        self._connect()
        if not shared.shutting_down and self.success:
            c = Connection(self.destination, 'i2p', self.s, 'i2p', False, self.destination)
            c.start()
            shared.connections.add(c)

    def _receive_line(self):
        line = receive_line(self.s)
        # logging.debug('I2PDialer <- ' + str(line))
        return line

    def _send(self, command):
        # logging.debug('I2PDialer -> ' + str(command))
        self.s.sendall(command)

    def _connect(self):
        self._send(b'HELLO VERSION MIN=3.0 MAX=3.3\n')
        self.version_reply = self._receive_line().split()
        if b'RESULT=OK' not in self.version_reply:
            logging.warning('Error while connecting to {}'.format(self.destination))
            self.success = False

        self._send(b'STREAM CONNECT ID=' + self.nick + b' DESTINATION=' + self.destination + b'\n')
        reply = self._receive_line().split(b' ')
        if b'RESULT=OK' not in reply:
            logging.warning('Error while connecting to {}'.format(self.destination))
            self.success = False
