# -*- coding: utf-8 -*-
import base64
import logging
import os
import socket
import threading

from i2p.util import receive_line, pub_from_priv
import shared


class I2PController(threading.Thread):
    def __init__(self, host='127.0.0.1', port=7656, dest_priv=b''):
        super().__init__(name='I2P Controller')

        self.host = host
        self.port = port
        self.nick = b'MiNode_' + base64.b16encode(os.urandom(4)).lower()

        self.s = socket.create_connection((self.host, self.port))

        self.version_reply = []

        self.init_connection()

        if dest_priv:
            self.dest_priv = dest_priv
            self.dest_pub = pub_from_priv(dest_priv)
        else:
            self.dest_priv = b''
            self.dest_pub = b''
            self.generate_destination()

        self.create_session()

    def _receive_line(self):
        line = receive_line(self.s)
        logging.debug('I2PController <- ' + str(line))
        return line

    def _send(self, command):
        logging.debug('I2PController -> ' + str(command))
        self.s.sendall(command)

    def init_connection(self):
        self._send(b'HELLO VERSION MIN=3.0 MAX=3.3\n')
        self.version_reply = self._receive_line().split()
        assert b'RESULT=OK' in self.version_reply

    def generate_destination(self):
        if b'VERSION=3.0' in self.version_reply:
            # We will now receive old DSA_SHA1 destination :(
            self._send(b'DEST GENERATE\n')
        else:
            self._send(b'DEST GENERATE SIGNATURE_TYPE=EdDSA_SHA512_Ed25519\n')

        reply = self._receive_line().split()
        for par in reply:
            if par.startswith(b'PUB='):
                self.dest_pub = par.replace(b'PUB=', b'')
            if par.startswith(b'PRIV='):
                self.dest_priv = par.replace(b'PRIV=', b'')
        assert self.dest_priv

    def create_session(self):
        self._send(b'SESSION CREATE STYLE=STREAM ID=' + self.nick + b' DESTINATION=' + self.dest_priv + b'\n')
        reply = self._receive_line().split()
        assert b'RESULT=OK' in reply

    def run(self):
        self.s.settimeout(1)
        while True:
            if not shared.shutting_down:
                try:
                    msg = self._receive_line().split(b' ')
                    if msg[0] == b'PING':
                        self._send(b'PONG ' + msg[1] + b'\n')
                except socket.timeout:
                    pass
            else:
                logging.debug('Shutting down I2P Controller')
                self.s.close()
                break
