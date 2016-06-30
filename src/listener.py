# -*- coding: utf-8 -*-
import logging
import socket
import threading

from connection import Connection
import shared


class Listener(threading.Thread):
    def __init__(self, host, port, family=socket.AF_INET):
        super().__init__(name='Listener')
        self.host = host
        self.port = port
        self.family = family
        self.s = socket.socket(self.family, socket.SOCK_STREAM)
        self.s.bind((self.host, self.port))

    def run(self):
        self.s.listen(1)
        self.s.settimeout(1)
        while True:
            try:
                conn, addr = self.s.accept()
                logging.info('Incoming connection from: {}:{}'.format(addr[0], addr[1]))
                with shared.connections_lock:
                    c = Connection(addr[0], addr[1], conn)
                    c.start()
                    shared.connections.add(c)
            except socket.timeout:
                pass
