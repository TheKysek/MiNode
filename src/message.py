# -*- coding: utf-8 -*-
import base64
import hashlib
import struct
import time

import shared
import structure


class Header(object):
    def __init__(self, command, payload_length, payload_checksum):
        self.command = command
        self.payload_length = payload_length
        self.payload_checksum = payload_checksum

    def __repr__(self):
        return 'type: header, command: "{}", payload_length: {}, payload_checksum: {}'\
            .format(self.command.decode(), self.payload_length, base64.b16encode(self.payload_checksum).decode())

    def to_bytes(self):
        b = b''
        b += shared.magic_bytes
        b += self.command.ljust(12, b'\x00')
        b += struct.pack('>L', self.payload_length)
        b += self.payload_checksum
        return b

    @classmethod
    def from_bytes(cls, b):
        magic_bytes, command, payload_length, payload_checksum = struct.unpack('>4s12sL4s', b)

        if magic_bytes != shared.magic_bytes:
            raise ValueError('magic_bytes do not match')

        command = command.rstrip(b'\x00')

        return cls(command, payload_length, payload_checksum)


class Message(object):
    def __init__(self, command, payload):
        self.command = command
        self.payload = payload

        self.payload_length = len(payload)
        self.payload_checksum = hashlib.sha512(payload).digest()[:4]

    def __repr__(self):
        return '{}, payload_length: {}, payload_checksum: {}'\
            .format(self.command.decode(), self.payload_length, base64.b16encode(self.payload_checksum).decode())

    def to_bytes(self):
        b = Header(self.command, self.payload_length, self.payload_checksum).to_bytes()
        b += self.payload
        return b

    @classmethod
    def from_bytes(cls, b):
        h = Header.from_bytes(b[:24])

        payload = b[24:]
        payload_length = len(payload)

        if payload_length != h.payload_length:
            raise ValueError('wrong payload length, expected {}, got {}'.format(h.payload_length, payload_length))

        payload_checksum = hashlib.sha512(payload).digest()[:4]

        if payload_checksum != h.payload_checksum:
            raise ValueError('wrong payload checksum, expected {}, got {}'.format(h.payload_checksum, payload_checksum))

        return cls(h.command, payload)


class Version(object):
    def __init__(self, host, port, protocol_version=shared.protocol_version, services=shared.services,
                 nonce=shared.nonce, user_agent=shared.user_agent):
        self.host = host
        self.port = port

        self.protocol_version = protocol_version
        self.services = services
        self.nonce = nonce
        self.user_agent = user_agent

    def __repr__(self):
        return 'version, protocol_version: {}, services: {}, host: {}, port: {}, nonce: {}, user_agent: {}'\
            .format(self.protocol_version, self.services, self.host, self.port, base64.b16encode(self.nonce).decode(), self.user_agent)

    def to_bytes(self):
        payload = b''
        payload += struct.pack('>I', self.protocol_version)
        payload += struct.pack('>Q', self.services)
        payload += struct.pack('>Q', int(time.time()))
        payload += structure.NetAddrNoPrefix(shared.services, self.host, self.port).to_bytes()
        payload += structure.NetAddrNoPrefix(shared.services, '127.0.0.1', 8444).to_bytes()
        payload += self.nonce
        payload += structure.VarInt(len(shared.user_agent)).to_bytes()
        payload += shared.user_agent
        payload += 2 * structure.VarInt(1).to_bytes()

        return Message(b'version', payload).to_bytes()

    @classmethod
    def from_bytes(cls, b):
        m = Message.from_bytes(b)

        payload = m.payload

        protocol_version, services, t, net_addr_remote, net_addr_local, nonce = \
            struct.unpack('>IQQ26s26s8s', payload[:80])

        net_addr_remote = structure.NetAddrNoPrefix.from_bytes(net_addr_remote)

        host = net_addr_remote.host
        port = net_addr_remote.port

        payload = payload[80:]

        user_agent_varint_length = structure.VarInt.length(payload[0])
        user_agent_length = structure.VarInt.from_bytes(payload[:user_agent_varint_length]).n

        payload = payload[user_agent_varint_length:]

        user_agent = payload[:user_agent_length]

        payload = payload[user_agent_length:]

        # Assume it is stream 1
        assert payload == b'\x01\x01'

        return cls(host, port, protocol_version, services, nonce, user_agent)


class Inv(object):
    def __init__(self, vectors):
        self.vectors = set(vectors)

    def __repr__(self):
        return 'inv, count: {}'.format(len(self.vectors))

    def to_bytes(self):
        return Message(b'inv', structure.VarInt(len(self.vectors)).to_bytes() + b''.join(self.vectors)).to_bytes()

    @classmethod
    def from_message(cls, m):
        payload = m.payload

        vector_count_varint_length = structure.VarInt.length(payload[0])
        vector_count = structure.VarInt.from_bytes(payload[:vector_count_varint_length]).n

        payload = payload[vector_count_varint_length:]

        vectors = set()

        while payload:
            vectors.add(payload[:32])
            payload = payload[32:]

        assert vector_count == len(vectors)

        return cls(vectors)


class GetData(object):
    def __init__(self, vectors):
        self.vectors = set(vectors)

    def __repr__(self):
        return 'getdata, count: {}'.format(len(self.vectors))

    def to_bytes(self):
        return Message(b'getdata', structure.VarInt(len(self.vectors)).to_bytes() + b''.join(self.vectors)).to_bytes()

    @classmethod
    def from_message(cls, m):
        payload = m.payload

        vector_count_varint_length = structure.VarInt.length(payload[0])
        vector_count = structure.VarInt.from_bytes(payload[:vector_count_varint_length]).n

        payload = payload[vector_count_varint_length:]

        vectors = set()

        while payload:
            vectors.add(payload[:32])
            payload = payload[32:]

        return cls(vectors)


class Addr(object):
    def __init__(self, addresses):
        self.addresses = addresses

    def __repr__(self):
        return 'addr, count: {}'.format(len(self.addresses))

    def to_bytes(self):
        return Message(b'addr', structure.VarInt(len(self.addresses)).to_bytes() + b''.join({addr.to_bytes() for addr in self.addresses})).to_bytes()

    @classmethod
    def from_message(cls, m):
        payload = m.payload

        addr_count_varint_length = structure.VarInt.length(payload[0])
        addr_count = structure.VarInt.from_bytes(payload[:addr_count_varint_length]).n

        payload = payload[addr_count_varint_length:]

        addresses = set()

        while payload:
            addresses.add(structure.NetAddr.from_bytes(payload[:38]))
            payload = payload[38:]

        return cls(addresses)
