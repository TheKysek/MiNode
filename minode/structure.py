# -*- coding: utf-8 -*-
import base64
import hashlib
import logging
import struct
import socket
import time

from . import shared


class VarInt(object):
    def __init__(self, n):
        self.n = n

    def to_bytes(self):
        if self.n < 0xfd:
            return struct.pack('>B', self.n)

        if self.n <= 0xffff:
            return b'\xfd' + struct.pack('>H', self.n)

        if self.n <= 0xffffffff:
            return b'\xfe' + struct.pack('>I', self.n)

        return b'\xff' + struct.pack('>Q', self.n)

    @staticmethod
    def length(b):
        if b == 0xfd:
            return 3
        if b == 0xfe:
            return 5
        if b == 0xff:
            return 9
        return 1

    @classmethod
    def from_bytes(cls, b):
        if cls.length(b[0]) > 1:
            b = b[1:]
        n = int.from_bytes(b, 'big')
        return cls(n)


class Object(object):
    def __init__(self, nonce, expires_time, object_type, version, stream_number, object_payload):
        self.nonce = nonce
        self.expires_time = expires_time
        self.object_type = object_type
        self.version = version
        self.stream_number = stream_number
        self.object_payload = object_payload
        self.vector = hashlib.sha512(hashlib.sha512(self.to_bytes()).digest()).digest()[:32]

    def __repr__(self):
        return 'object, vector: {}'.format(base64.b16encode(self.vector).decode())

    @classmethod
    def from_message(cls, m):
        payload = m.payload
        nonce, expires_time, object_type = struct.unpack('>8sQL', payload[:20])
        payload = payload[20:]
        version_varint_length = VarInt.length(payload[0])
        version = VarInt.from_bytes(payload[:version_varint_length]).n
        payload = payload[version_varint_length:]
        stream_number_varint_length = VarInt.length(payload[0])
        stream_number = VarInt.from_bytes(payload[:stream_number_varint_length]).n
        payload = payload[stream_number_varint_length:]
        return cls(nonce, expires_time, object_type, version, stream_number, payload)

    def to_bytes(self):
        payload = b''
        payload += self.nonce
        payload += struct.pack('>QL', self.expires_time, self.object_type)
        payload += VarInt(self.version).to_bytes() + VarInt(self.stream_number).to_bytes()
        payload += self.object_payload
        return payload

    def is_expired(self):
        return self.expires_time + 3 * 3600 < time.time()

    def is_valid(self):
        if self.is_expired():
            logging.debug('Invalid object {}, reason: expired'.format(base64.b16encode(self.vector).decode()))
            return False
        if self.expires_time > time.time() + 28 * 24 * 3600 + 3 * 3600:
            logging.warning('Invalid object {}, reason: end of life too far in the future'.format(base64.b16encode(self.vector).decode()))
            return False
        if len(self.object_payload) > 2**18:
            logging.warning('Invalid object {}, reason: payload is too long'.format(base64.b16encode(self.vector).decode()))
            return False
        if self.stream_number != 1:
            logging.warning('Invalid object {}, reason: not in stream 1'.format(base64.b16encode(self.vector).decode()))
            return False
        data = self.to_bytes()[8:]
        length = len(data) + 8 + shared.payload_length_extra_bytes
        dt = max(self.expires_time - time.time(), 0)
        h = hashlib.sha512(data).digest()
        pow_value = int.from_bytes(hashlib.sha512(hashlib.sha512(self.nonce + h).digest()).digest()[:8], 'big')
        target = self.pow_target()
        if target < pow_value:
            logging.warning('Invalid object {}, reason: insufficient pow'.format(base64.b16encode(self.vector).decode()))
            return False
        return True

    def pow_target(self):
        data = self.to_bytes()[8:]
        length = len(data) + 8 + shared.payload_length_extra_bytes
        dt = max(self.expires_time - time.time(), 0)
        return int(2 ** 64 / (shared.nonce_trials_per_byte * (length + (dt * length) / (2 ** 16))))

    def pow_initial_hash(self):
        return hashlib.sha512(self.to_bytes()[8:]).digest()


class NetAddrNoPrefix(object):
    def __init__(self, services, host, port):
        self.services = services
        self.host = host
        self.port = port

    def __repr__(self):
        return 'net_addr_no_prefix, services: {}, host: {}, port {}'.format(self.services, self.host, self.port)

    def to_bytes(self):
        b = b''
        b += struct.pack('>Q', self.services)
        try:
            host = socket.inet_pton(socket.AF_INET, self.host)
            b += b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF' + host
        except socket.error:
            b += socket.inet_pton(socket.AF_INET6, self.host)
        b += struct.pack('>H', int(self.port))
        return b

    @classmethod
    def from_bytes(cls, b):
        services, host, port = struct.unpack('>Q16sH', b)
        if host.startswith(b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF'):
            host = socket.inet_ntop(socket.AF_INET, host[-4:])
        else:
            host = socket.inet_ntop(socket.AF_INET6, host)
        return cls(services, host, port)


class NetAddr(object):
    def __init__(self, services, host, port, stream=shared.stream):
        self.stream = stream
        self.services = services
        self.host = host
        self.port = port

    def __repr__(self):
        return 'net_addr, stream: {}, services: {}, host: {}, port {}'\
            .format(self.stream, self.services, self.host, self.port)

    def to_bytes(self):
        b = b''
        b += struct.pack('>Q', int(time.time()))
        b += struct.pack('>I', self.stream)
        b += NetAddrNoPrefix(self.services, self.host, self.port).to_bytes()
        return b

    @classmethod
    def from_bytes(cls, b):
        t, stream, net_addr = struct.unpack('>QI26s', b)
        n = NetAddrNoPrefix.from_bytes(net_addr)
        return cls(n.services, n.host, n.port, stream)
