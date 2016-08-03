# -*- coding: utf-8 -*-
import errno
import logging
import os
import random
import select
import socket
import ssl
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

        self.tls = False

        self.verack_received = False
        self.verack_sent = False

        self.host = host
        self.port = int(port)

        self.s = s

        self.remote_version = None

        self.server = bool(s)

        if self.server:
            self.status = 'connected'

        self.buffer_receive = b''
        self.buffer_send = b''

        self.next_message_size = shared.header_length
        self.next_header = True
        self.on_connection_fully_established_scheduled = False

        self.last_message_received = time.time()
        self.last_message_sent = time.time()

    def run(self):
        if self.s is None:
            self._connect()
        if self.status != 'connected':
            return
        self.s.settimeout(0)
        if not self.server:
            self.send_queue.put(message.Version(self.host, self.port))
        while True:
            time.sleep(0.3)
            data = True
            try:
                data = self.s.recv(self.next_message_size - len(self.buffer_receive))
                self.buffer_receive += data
            except ssl.SSLWantReadError:
                pass
            except socket.error as e:
                err = e.args[0]
                if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                    pass
                else:
                    raise
            except ConnectionResetError:
                logging.debug('Disconnecting from {}:{}. Reason: ConnectionResetError'.format(self.host, self.port))
                data = None
            self._process_buffer_receive()
            self._request_objects()
            self._process_queue()
            self._send_data()
            if time.time() - self.last_message_received > shared.timeout:
                logging.debug(
                    'Disconnecting from {}:{}. Reason: time.time() - self.last_message_received > shared.timeout'.format(
                        self.host, self.port))
                data = None
            if time.time() - self.last_message_received > 30 and self.status != 'fully_established':
                logging.debug(
                    'Disconnecting from {}:{}. Reason: time.time() - self.last_message_received > 30 and self.status != \'fully_established\''.format(
                        self.host, self.port))
                data = None
            if time.time() - self.last_message_sent > 300 and self.status == 'fully_established':
                self.send_queue.put(message.Message(b'pong', b''))
            if self.on_connection_fully_established_scheduled and not (self.buffer_send or self.buffer_receive):
                self._on_connection_fully_established()
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

    def _send_data(self):
        try:
            amount = self.s.send(self.buffer_send[:1000])
            self.buffer_send = self.buffer_send[amount:]
        except (BlockingIOError, ssl.SSLWantWriteError):
            pass

    def _do_tls_handshake(self):
        logging.debug('Initializing TLS connection with {}:{}'.format(self.host, self.port))
        self.s = ssl.wrap_socket(self.s, keyfile=os.path.join(shared.source_directory, 'tls', 'key.pem'),
                                 certfile=os.path.join(shared.source_directory, 'tls', 'cert.pem'),
                                 server_side=self.server, ssl_version=ssl.PROTOCOL_TLSv1, do_handshake_on_connect=False,
                                 ciphers='AECDH-AES256-SHA', suppress_ragged_eofs=True)
        if hasattr(self.s, "context"):
            self.s.context.set_ecdh_curve("secp256k1")
        while True:
            try:
                self.s.do_handshake()
                break
            except ssl.SSLWantReadError:
                select.select([self.s], [], [])
            except ssl.SSLWantWriteError:
                select.select([], [self.s], [])
            except Exception as e:
                logging.error(e)
                break
        self.tls = True
        logging.debug('Established TLS connection with {}:{}'.format(self.host, self.port))

    def _send_message(self, m):
        if type(m) == message.Message and m.command == b'object':
            logging.debug('{}:{} <- {}'.format(self.host, self.port, structure.Object.from_message(m)))
        else:
            logging.debug('{}:{} <- {}'.format(self.host, self.port, m))
        self.buffer_send += m.to_bytes()

    def _on_connection_fully_established(self):
        logging.info('Established Bitmessage protocol connection to {}:{}'.format(self.host, self.port))
        self.on_connection_fully_established_scheduled = False
        if self.remote_version.services & 2:  # NODE_SSL
            self._do_tls_handshake()
        with shared.objects_lock:
            if len(shared.objects) > 0:
                self.send_queue.put(message.Inv({vector for vector in shared.objects.keys() if shared.objects[vector].expires_time > time.time()}))
        addr = {structure.NetAddr(c.remote_version.services, c.host, c.port) for c in shared.connections.copy() if not c.server and c.status == 'fully_established'}
        if len(addr) != 0:
            self.send_queue.put(message.Addr(addr))
        self.status = 'fully_established'

    def _process_queue(self):
        while not self.send_queue.empty():
            m = self.send_queue.get()
            if m:
                if m == 'fully_established':
                    self.on_connection_fully_established_scheduled = True
                else:
                    self._send_message(m)
                    self.last_message_sent = time.time()
            else:
                self.status = 'disconnecting'
                break

    def _process_buffer_receive(self):
        while len(self.buffer_receive) >= self.next_message_size:
            if self.next_header:
                self.next_header = False
                h = message.Header.from_bytes(self.buffer_receive[:shared.header_length])
                self.next_message_size += h.payload_length
            else:
                m = message.Message.from_bytes(self.buffer_receive[:self.next_message_size])

                self.next_header = True
                self.buffer_receive = self.buffer_receive[self.next_message_size:]
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
                self.verack_sent = True
                self.remote_version = version
                if not self.server:
                    self.send_queue.put('fully_established')
                    shared.address_advertise_queue.put(structure.NetAddr(version.services, self.host, self.port))
                    shared.node_pool.add((self.host, self.port))
                shared.address_advertise_queue.put(structure.NetAddr(shared.services, version.host, shared.listening_port))
                if self.server:
                    self.send_queue.put(message.Version(self.host, self.port))
        elif m.command == b'verack':
            self.verack_received = True
            logging.debug('{}:{} -> {}'.format(self.host, self.port, 'verack'))
            if self.server:
                self.send_queue.put('fully_established')

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
        elif m.command == b'addr':
            addr = message.Addr.from_message(m)
            logging.debug('{}:{} -> {}'.format(self.host, self.port, addr))
            for a in addr.addresses:
                shared.unchecked_node_pool.add((a.host, a.port))
        elif m.command == b'ping':
            logging.debug('{}:{} -> ping'.format(self.host, self.port))
            self.send_queue.put(message.Message(b'pong', b''))
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
