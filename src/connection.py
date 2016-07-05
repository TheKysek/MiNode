# -*- coding: utf-8 -*-
import logging
import random
import socket
import threading
import queue
import time

import message
import shared
import structure


class Connection(threading.Thread):
    def __init__(self, host, port, s=None):
        super().__init__(name='Connection to {}:{}'.format(host, port))

        self.send_queue = queue.Queue()

        self.vectors_to_get = set()

        self.status = 'ready'
        self.sent_verack = False
        self.sent_big_inv_message = False

        self.host = host
        self.port = int(port)

        self.s = s

        self.remote_version = None

        self.server = bool(s)

        if self.server:
            self.status = 'connected'

        self.buffer = b''
        self.next_message_size = shared.header_length
        self.next_header = True

        self.last_message_received = time.time()
        self.last_message_sent = time.time()

    def run(self):
        if self.s is None:
            self._connect()
        if self.status != 'connected':
            return
        self.s.settimeout(1)
        if not self.server:
            self.send_queue.put(message.Version(self.host, self.port))
        while True:
            data = True
            try:
                data = self.s.recv(1014)
                self.buffer += data
            except socket.timeout:
                if time.time() - self.last_message_received > shared.timeout:
                    data = None
                if time.time() - self.last_message_received > 20 and self.status != 'verack_received':
                    data = None
                if time.time() - self.last_message_sent > 60 and self.status == 'verack_received':
                    self.send_queue.put(message.Message(b'alive', b''))
                if not self.sent_big_inv_message and self.status == 'verack_received' and self.sent_verack:
                    self._send_big_inv()
            except ConnectionResetError:
                data = None
            self._process_buffer()
            self._request_objects()
            self._process_queue()
            if self.status == 'disconnecting':
                data = None
            if not data:
                self.status = 'disconnected'
                self.s.close()
                logging.info('Disconnected from {}:{}'.format(self.host, self.port))
                break

    def _connect(self):
        logging.info('Connecting to {}:{}'.format(self.host, self.port))

        try:
            self.s = socket.create_connection((self.host, self.port))
            self.status = 'connected'
            logging.debug('Established TCP connection to {}:{}'.format(self.host, self.port))
        except Exception as e:
            logging.warning('Connection to {}:{} failed'.format(self.host, self.port))
            logging.warning(e)

            self.status = 'failed'

    def _send_message(self, m):
        if type(m) == message.Message and m.command == b'object':
            logging.debug('{}:{} <- {}'.format(self.host, self.port, structure.Object.from_message(m)))
        else:
            logging.debug('{}:{} <- {}'.format(self.host, self.port, m))
        self.s.settimeout(60)
        self.s.sendall(m.to_bytes())
        self.s.settimeout(1)

    def _send_big_inv(self):
        with shared.objects_lock:
            self.send_queue.put(message.Inv({vector for vector in shared.objects.keys() if shared.objects[vector].expires_time > time.time()}))
        addr = {structure.NetAddr(1, c.host, c.port) for c in shared.connections.copy() if not c.server}
        if len(addr) != 0:
            self.send_queue.put(message.Addr(addr))
        self.sent_big_inv_message = True

    def _process_queue(self):
        while not self.send_queue.empty():
            m = self.send_queue.get()
            if m:
                self._send_message(m)
                self.last_message_sent = time.time()
            else:
                self.status = 'disconnecting'
                break

    def _process_buffer(self):
        while len(self.buffer) >= self.next_message_size:
            if self.next_header:
                self.next_header = False
                h = message.Header.from_bytes(self.buffer[:shared.header_length])
                self.next_message_size += h.payload_length
            else:
                m = message.Message.from_bytes(self.buffer[:self.next_message_size])

                self.next_header = True
                self.buffer = self.buffer[self.next_message_size:]
                self.next_message_size = shared.header_length
                self.last_message_received = time.time()
                self._process_message(m)

    def _process_message(self, m):
        if m.command == b'version':
            version = message.Version.from_bytes(m.to_bytes())
            logging.debug('{}:{} -> {}'.format(self.host, self.port, str(version)))
            if version.protocol_version != shared.protocol_version or version.nonce == shared.nonce:
                self.status = 'disconnecting'
                self.send_queue.put(None)
            else:
                self.send_queue.put(message.Message(b'verack', b''))
                self.sent_verack = True
                self.remote_version = version
                if not self.server:
                    shared.address_advertise_queue.put(structure.NetAddr(version.services, self.host, self.port))
                    shared.node_pool.add((self.host, self.port))
                shared.address_advertise_queue.put(structure.NetAddr(shared.services, version.host, shared.listening_port))
            if self.server:
                self.send_queue.put(message.Version(self.host, self.port))
        elif m.command == b'verack':
            self.status = 'verack_received'
            logging.debug('{}:{} -> {}'.format(self.host, self.port, 'verack'))
            logging.info('Established Bitmessage protocol connection to {}:{}'.format(self.host, self.port))
        elif m.command == b'inv':
            inv = message.Inv.from_message(m)
            logging.debug('{}:{} -> {}'.format(self.host, self.port, inv))
            to_get = inv.vectors.copy()
            to_get.difference_update(shared.objects.keys())
            to_get.difference_update(shared.requested_objects)
            self.vectors_to_get.update(to_get)
        elif m.command == b'object':
            obj = structure.Object.from_message(m)
            logging.debug('{}:{} -> {}'.format(self.host, self.port, obj))
            if obj.is_valid() and obj.vector not in shared.objects:
                with shared.objects_lock:
                    shared.objects[obj.vector] = obj
                shared.vector_advertise_queue.put(obj.vector)
        elif m.command == b'getdata':
            getdata = message.GetData.from_message(m)
            logging.debug('{}:{} -> {}'.format(self.host, self.port, getdata))
            for vector in getdata.vectors:
                if vector in shared.objects:
                    self.send_queue.put(message.Message(b'object', shared.objects[vector].to_bytes()))
        elif m.command == b'addr': #  TODO fix ;P
            addr = message.Addr.from_message(m)
            logging.debug('{}:{} -> {}'.format(self.host, self.port, addr))
            for a in addr.addresses:
                shared.unchecked_node_pool.add((a.host, a.port))
        else:
            logging.debug('{}:{} -> {}'.format(self.host, self.port, m))

    def _request_objects(self):
        if self.vectors_to_get:
            if len(self.vectors_to_get) > 50000:
                pack = random.sample(self.vectors_to_get, 50000)
                self.send_queue.put(message.GetData(pack))
                self.vectors_to_get.difference_update(pack)
                if shared.conserve_bandwidth:
                    with shared.requested_objects_lock:
                        shared.requested_objects.update(pack)
            else:
                self.send_queue.put(message.GetData(self.vectors_to_get))
                if shared.conserve_bandwidth:
                    with shared.requested_objects_lock:
                        shared.requested_objects.update(self.vectors_to_get)
                self.vectors_to_get.clear()