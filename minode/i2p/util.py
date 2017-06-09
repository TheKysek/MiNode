# -*- coding: utf-8 -*-
import base64
import hashlib


def receive_line(s):
    data = b''
    while b'\n' not in data:
        d = s.recv(4096)
        if not d:
            raise ConnectionResetError
        data += d
    data = data.splitlines()
    return data[0]


def pub_from_priv(priv):
    priv = base64.b64decode(priv, altchars=b'-~')
    # 256 for public key + 128 for signing key + 3 for certificate header + value of bytes priv[385:387]
    pub = priv[:387 + int.from_bytes(priv[385:387], byteorder='big')]
    pub = base64.b64encode(pub, altchars=b'-~')
    return pub


def b32_from_pub(pub):
    return base64.b32encode(hashlib.sha256(base64.b64decode(pub, b'-~')).digest()).replace(b"=", b"").lower() + b'.b32.i2p'
