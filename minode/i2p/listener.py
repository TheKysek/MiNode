# -*- coding: utf-8 -*-
import logging
import socket
import threading

from .util import receive_line


class I2PListener(threading.Thread):
    def __init__(self, state, nick, host='127.0.0.1', port=7656):
        super().__init__(name='I2P Listener')

        self.state = state
        self.host = host
        self.port = port
        self.nick = nick

        self.s = None

        self.version_reply = []

        self.new_socket()

    def _receive_line(self):
        line = receive_line(self.s)
        # logging.debug('I2PListener <- %s', line)
        return line

    def _send(self, command):
        # logging.debug('I2PListener -> %s', command)
        self.s.sendall(command)

    def new_socket(self):
        self.s = socket.create_connection((self.host, self.port))
        self._send(b'HELLO VERSION MIN=3.0 MAX=3.3\n')
        self.version_reply = self._receive_line().split()
        assert b'RESULT=OK' in self.version_reply

        self._send(b'STREAM ACCEPT ID=' + self.nick + b'\n')
        reply = self._receive_line().split(b' ')
        assert b'RESULT=OK' in reply

        self.s.settimeout(1)

    def run(self):
        while not self.state.shutting_down:
            try:
                destination = self._receive_line().split()[0]
                logging.info(
                    'Incoming I2P connection from: %s', destination.decode())

                hosts = set()
                for c in self.state.connections.copy():
                    hosts.add(c.host)
                for d in self.state.i2p_dialers.copy():
                    hosts.add(d.destination)
                if destination in hosts:
                    logging.debug('Rejecting duplicate I2P connection.')
                    self.s.close()
                else:
                    c = self.state.connection(
                        destination, 'i2p', self.s, 'i2p', True, destination)
                    c.start()
                    self.state.connections.add(c)
                self.new_socket()
            except socket.timeout:
                pass
        logging.debug('Shutting down I2P Listener')
