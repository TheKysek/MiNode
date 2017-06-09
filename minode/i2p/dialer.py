# -*- coding: utf-8 -*-
import logging
import socket

from connection import Connection
from i2p.util import receive_line


class I2PDialer(object):
    def __init__(self, destination, nick, host='127.0.0.1', port=7656):

        self.host = host
        self.port = port

        self.nick = nick
        self.destination = destination

        self.s = socket.create_connection((self.host, self.port))

        self.version_reply = []

        self._connect()

    def _receive_line(self):
        line = receive_line(self.s)
        logging.debug('I2PDialer <-' + str(line))
        return line

    def _send(self, command):
        logging.debug('I2PDialer ->' + str(command))
        self.s.sendall(command)

    def _connect(self):
        self._send(b'HELLO VERSION MIN=3.0 MAX=3.3\n')
        self.version_reply = self._receive_line().split()
        assert b'RESULT=OK' in self.version_reply

        self._send(b'STREAM CONNECT ID=' + self.nick + b' DESTINATION=' + self.destination + b'\n')
        reply = self._receive_line().split(b' ')
        assert b'RESULT=OK' in reply

    def get_connection(self):
        return Connection(self.destination, 'i2p', self.s, 'i2p', False, self.destination)
