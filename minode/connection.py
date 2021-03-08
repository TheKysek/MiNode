# -*- coding: utf-8 -*-
import base64
import errno
import logging
import random
import select
import socket
import ssl
import threading
import queue
import time

from . import message, shared, structure


class Connection(threading.Thread):
    def __init__(
        self, host, port, s=None, network='ip', server=False,
        i2p_remote_dest=b''
    ):
        self.host = host
        self.port = port
        self.network = network
        self.i2p_remote_dest = i2p_remote_dest

        if self.network == 'i2p':
            self.host_print = self.i2p_remote_dest[:8].decode()
        else:
            self.host_print = self.host

        super().__init__(name='Connection to {}:{}'.format(host, port))

        self.send_queue = queue.Queue()

        self.vectors_to_get = set()
        self.vectors_to_send = set()

        self.vectors_requested = dict()

        self.status = 'ready'

        self.tls = False

        self.verack_received = False
        self.verack_sent = False

        self.s = s

        self.remote_version = None

        self.server = server

        if bool(s):
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
            if self.network == 'ip':
                self.send_queue.put(message.Version(self.host, self.port))
            else:
                self.send_queue.put(message.Version('127.0.0.1', 7656))
        while True:
            if (
                self.on_connection_fully_established_scheduled
                and not (self.buffer_send or self.buffer_receive)
            ):
                self._on_connection_fully_established()
            data = True
            try:
                if self.status == 'fully_established':
                    data = self.s.recv(4096)
                    self.buffer_receive += data
                    if data and len(self.buffer_receive) < 4000000:
                        continue
                else:
                    data = self.s.recv(
                        self.next_message_size - len(self.buffer_receive))
                    self.buffer_receive += data
            except ssl.SSLWantReadError:
                if self.status == 'fully_established':
                    self._request_objects()
                    self._send_objects()
            except socket.error as e:
                err = e.args[0]
                if err in (errno.EAGAIN, errno.EWOULDBLOCK):
                    if self.status == 'fully_established':
                        self._request_objects()
                        self._send_objects()
                else:
                    logging.debug(
                        'Disconnecting from %s:%s. Reason: %s',
                        self.host_print, self.port, e)
                    data = None
            except ConnectionResetError:
                logging.debug(
                    'Disconnecting from %s:%s. Reason: ConnectionResetError',
                    self.host_print, self.port)
                self.status = 'disconnecting'
            self._process_buffer_receive()
            self._process_queue()
            self._send_data()
            if time.time() - self.last_message_received > shared.timeout:
                logging.debug(
                    'Disconnecting from %s:%s. Reason:'
                    ' time.time() - self.last_message_received'
                    ' > shared.timeout', self.host_print, self.port)
                self.status = 'disconnecting'
            if (
                time.time() - self.last_message_received > 30
                and self.status != 'fully_established'
                and self.status != 'disconnecting'
            ):
                logging.debug(
                    'Disconnecting from %s:%s. Reason:'
                    ' time.time() - self.last_message_received > 30'
                    ' and self.status != "fully_established"',
                    self.host_print, self.port)
                self.status = 'disconnecting'
            if (
                time.time() - self.last_message_sent > 300
                and self.status == 'fully_established'
            ):
                self.send_queue.put(message.Message(b'pong', b''))
            if self.status == 'disconnecting' or shared.shutting_down:
                data = None
            if not data:
                self.status = 'disconnected'
                self.s.close()
                logging.info(
                    'Disconnected from %s:%s', self.host_print, self.port)
                break
            time.sleep(0.2)

    def _connect(self):
        logging.debug('Connecting to %s:%s', self.host_print, self.port)

        try:
            self.s = socket.create_connection((self.host, self.port), 10)
            self.status = 'connected'
            logging.info(
                'Established TCP connection to %s:%s',
                self.host_print, self.port)
        except Exception as e:
            logging.warning(
                'Connection to %s:%s failed. Reason: %s',
                self.host_print, self.port, e)
            self.status = 'failed'

    def _send_data(self):
        if self.buffer_send and self:
            try:
                amount = self.s.send(self.buffer_send)
                self.buffer_send = self.buffer_send[amount:]
            except (BlockingIOError, ssl.SSLWantWriteError):
                pass
            except (
                BrokenPipeError, ConnectionResetError, ssl.SSLError, OSError
            ) as e:
                logging.debug(
                    'Disconnecting from %s:%s. Reason: %s',
                    self.host_print, self.port, e)
                self.status = 'disconnecting'

    def _do_tls_handshake(self):
        logging.debug(
            'Initializing TLS connection with %s:%s',
            self.host_print, self.port)

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        if (
            ssl.OPENSSL_VERSION_NUMBER >= 0x10100000
            and not ssl.OPENSSL_VERSION.startswith("LibreSSL")
        ):  # OpenSSL>=1.1
            context.set_ciphers('AECDH-AES256-SHA@SECLEVEL=0')
        else:
            context.set_ciphers('AECDH-AES256-SHA')

        context.set_ecdh_curve("secp256k1")
        context.options = (
            ssl.OP_ALL | ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3
            | ssl.OP_SINGLE_ECDH_USE | ssl.OP_CIPHER_SERVER_PREFERENCE)

        self.s = context.wrap_socket(
            self.s, server_side=self.server, do_handshake_on_connect=False)

        while True:
            try:
                self.s.do_handshake()
                break
            except ssl.SSLWantReadError:
                select.select([self.s], [], [])
            except ssl.SSLWantWriteError:
                select.select([], [self.s], [])
            except Exception as e:
                logging.debug(
                    'Disconnecting from %s:%s. Reason: %s',
                    self.host_print, self.port, e)
                self.status = 'disconnecting'
                break
        self.tls = True
        logging.debug(
            'Established TLS connection with %s:%s',
            self.host_print, self.port)

    def _send_message(self, m):
        if isinstance(m, message.Message) and m.command == b'object':
            logging.debug(
                '%s:%s <- %s',
                self.host_print, self.port, structure.Object.from_message(m))
        else:
            logging.debug('%s:%s <- %s', self.host_print, self.port, m)
        self.buffer_send += m.to_bytes()

    def _on_connection_fully_established(self):
        logging.info(
            'Established Bitmessage protocol connection to %s:%s',
            self.host_print, self.port)
        self.on_connection_fully_established_scheduled = False
        if self.remote_version.services & 2 and self.network == 'ip':
            self._do_tls_handshake()  # NODE_SSL

        addr = {
            structure.NetAddr(c.remote_version.services, c.host, c.port)
            for c in shared.connections if c.network != 'i2p'
            and c.server is False and c.status == 'fully_established'}
        if len(shared.node_pool) > 10:
            addr.update({
                structure.NetAddr(1, a[0], a[1])
                for a in random.sample(shared.node_pool, 10)})
        if len(shared.unchecked_node_pool) > 10:
            addr.update({
                structure.NetAddr(1, a[0], a[1])
                for a in random.sample(shared.unchecked_node_pool, 10)})
        if len(addr) != 0:
            self.send_queue.put(message.Addr(addr))

        with shared.objects_lock:
            if len(shared.objects) > 0:
                to_send = {
                    vector for vector in shared.objects.keys()
                    if shared.objects[vector].expires_time > time.time()}
                while len(to_send) > 0:
                    if len(to_send) > 10000:
                        # We limit size of inv messaged to 10000 entries
                        # because they might time out in very slow networks (I2P)
                        pack = random.sample(to_send, 10000)
                        self.send_queue.put(message.Inv(pack))
                        to_send.difference_update(pack)
                    else:
                        self.send_queue.put(message.Inv(to_send))
                        to_send.clear()
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
                try:
                    h = message.Header.from_bytes(
                        self.buffer_receive[:shared.header_length])
                except ValueError as e:
                    self.status = 'disconnecting'
                    logging.warning(
                        'Received malformed message from %s:%s: %s',
                        self.host_print, self.port, e)
                    break
                self.next_message_size += h.payload_length
            else:
                try:
                    m = message.Message.from_bytes(
                        self.buffer_receive[:self.next_message_size])
                except ValueError as e:
                    self.status = 'disconnecting'
                    logging.warning(
                        'Received malformed message from %s:%s, %s',
                        self.host_print, self.port, e)
                    break
                self.next_header = True
                self.buffer_receive = self.buffer_receive[
                    self.next_message_size:]
                self.next_message_size = shared.header_length
                self.last_message_received = time.time()
                try:
                    self._process_message(m)
                except ValueError as e:
                    self.status = 'disconnecting'
                    logging.warning(
                        'Received malformed message from %s:%s: %s',
                        self.host_print, self.port, e)
                    break

    def _process_message(self, m):
        if m.command == b'version':
            version = message.Version.from_bytes(m.to_bytes())
            logging.debug('%s:%s -> %s', self.host_print, self.port, version)
            if (
                version.protocol_version != shared.protocol_version
                or version.nonce == shared.nonce
            ):
                self.status = 'disconnecting'
                self.send_queue.put(None)
            else:
                self.send_queue.put(message.Message(b'verack', b''))
                self.verack_sent = True
                self.remote_version = version
                if not self.server:
                    self.send_queue.put('fully_established')
                    if self.network == 'ip':
                        shared.address_advertise_queue.put(structure.NetAddr(
                            version.services, self.host, self.port))
                        shared.node_pool.add((self.host, self.port))
                    elif self.network == 'i2p':
                        shared.i2p_node_pool.add((self.host, 'i2p'))
                if self.network == 'ip':
                    shared.address_advertise_queue.put(structure.NetAddr(
                        shared.services, version.host, shared.listening_port))
                if self.server:
                    if self.network == 'ip':
                        self.send_queue.put(
                            message.Version(self.host, self.port))
                    else:
                        self.send_queue.put(message.Version('127.0.0.1', 7656))

        elif m.command == b'verack':
            self.verack_received = True
            logging.debug(
                '%s:%s -> %s', self.host_print, self.port, 'verack')
            if self.server:
                self.send_queue.put('fully_established')

        elif m.command == b'inv':
            inv = message.Inv.from_message(m)
            logging.debug('%s:%s -> %s', self.host_print, self.port, inv)
            to_get = inv.vectors.copy()
            to_get.difference_update(shared.objects.keys())
            self.vectors_to_get.update(to_get)
            # Do not send objects they already have.
            self.vectors_to_send.difference_update(inv.vectors)

        elif m.command == b'object':
            obj = structure.Object.from_message(m)
            logging.debug('%s:%s -> %s', self.host_print, self.port, obj)
            self.vectors_requested.pop(obj.vector, None)
            self.vectors_to_get.discard(obj.vector)
            if obj.is_valid() and obj.vector not in shared.objects:
                with shared.objects_lock:
                    shared.objects[obj.vector] = obj
                if (
                    obj.object_type == shared.i2p_dest_obj_type
                    and obj.version == shared.i2p_dest_obj_version
                ):
                    dest = base64.b64encode(obj.object_payload, altchars=b'-~')
                    logging.debug(
                        'Received I2P destination object,'
                        ' adding to i2p_unchecked_node_pool')
                    logging.debug(dest)
                    shared.i2p_unchecked_node_pool.add((dest, 'i2p'))
                shared.vector_advertise_queue.put(obj.vector)

        elif m.command == b'getdata':
            getdata = message.GetData.from_message(m)
            logging.debug('%s:%s -> %s', self.host_print, self.port, getdata)
            self.vectors_to_send.update(getdata.vectors)

        elif m.command == b'addr':
            addr = message.Addr.from_message(m)
            logging.debug('%s:%s -> %s', self.host_print, self.port, addr)
            for a in addr.addresses:
                shared.unchecked_node_pool.add((a.host, a.port))

        elif m.command == b'ping':
            logging.debug('%s:%s -> ping', self.host_print, self.port)
            self.send_queue.put(message.Message(b'pong', b''))

        elif m.command == b'error':
            logging.error(
                '%s:%s -> error: %s', self.host_print, self.port, m.payload)

        else:
            logging.debug('%s:%s -> %s', self.host_print, self.port, m)

    def _request_objects(self):
        if self.vectors_to_get and len(self.vectors_requested) < 100:
            self.vectors_to_get.difference_update(shared.objects.keys())
            if self.vectors_to_get:
                if len(self.vectors_to_get) > 64:
                    pack = random.sample(self.vectors_to_get, 64)
                    self.send_queue.put(message.GetData(pack))
                    self.vectors_requested.update({
                        vector: time.time() for vector in pack
                        if vector not in self.vectors_requested})
                    self.vectors_to_get.difference_update(pack)
                else:
                    self.send_queue.put(message.GetData(self.vectors_to_get))
                    self.vectors_requested.update({
                        vector: time.time() for vector in self.vectors_to_get
                        if vector not in self.vectors_requested})
                    self.vectors_to_get.clear()
        if self.vectors_requested:
            self.vectors_requested = {
                vector: t for vector, t in self.vectors_requested.items()
                if vector not in shared.objects and t > time.time() - 15 * 60}
            to_re_request = {
                vector for vector, t in self.vectors_requested.items()
                if t < time.time() - 10 * 60}
            if to_re_request:
                self.vectors_to_get.update(to_re_request)
                logging.debug(
                    'Re-requesting %i objects from %s:%s',
                    len(to_re_request), self.host_print, self.port)

    def _send_objects(self):
        if self.vectors_to_send:
            if len(self.vectors_to_send) > 16:
                to_send = random.sample(self.vectors_to_send, 16)
                self.vectors_to_send.difference_update(to_send)
            else:
                to_send = self.vectors_to_send.copy()
                self.vectors_to_send.clear()
            with shared.objects_lock:
                for vector in to_send:
                    obj = shared.objects.get(vector, None)
                    if obj:
                        self.send_queue.put(
                            message.Message(b'object', obj.to_bytes()))


shared.connection = Connection
