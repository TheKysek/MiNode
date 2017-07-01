# -*- coding: utf-8 -*-
import logging
import socket
import threading

from connection import Connection
from i2p.util import receive_line
import shared


class I2PListener(threading.Thread):
    def __init__(self, nick, host='127.0.0.1', port=7656):
        super().__init__(name='I2P Listener')

        self.host = host
        self.port = port
        self.nick = nick

        self.s = None

        self.version_reply = []

        self.create_socket()

    def _receive_line(self):
        line = receive_line(self.s)
        # logging.debug('I2PListener <- ' + str(line))
        return line

    def _send(self, command):
        # logging.debug('I2PListener -> ' + str(command))
        self.s.sendall(command)

    def create_socket(self):
        self.s = socket.create_connection((self.host, self.port))
        self._send(b'HELLO VERSION MIN=3.0 MAX=3.3\n')
        self.version_reply = self._receive_line().split()
        assert b'RESULT=OK' in self.version_reply

        self._send(b'STREAM ACCEPT ID=' + self.nick + b'\n')
        reply = self._receive_line().split(b' ')
        assert b'RESULT=OK' in reply

        self.s.settimeout(1)

    def run(self):
        while not shared.shutting_down:
            try:
                destination = self._receive_line().split()[0]
                logging.info('Incoming I2P connection from: {}'.format(destination.decode()))
                c = Connection(destination, 'i2p', self.s, 'i2p', True, destination)
                c.start()
                shared.connections.add(c)
                self.create_socket()
            except socket.timeout:
                pass
        logging.debug('Shutting down I2P Listener')
