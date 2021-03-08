import base64
import hashlib
import logging
import multiprocessing
import struct
import threading
import time

from . import shared, structure


def _pow_worker(target, initial_hash, q):
    nonce = 0
    logging.debug(
        'target: %s, initial_hash: %s',
        target, base64.b16encode(initial_hash).decode())
    trial_value = target + 1

    while trial_value > target:
        nonce += 1
        trial_value = struct.unpack('>Q', hashlib.sha512(hashlib.sha512(
            struct.pack('>Q', nonce) + initial_hash).digest()).digest()[:8])[0]

    q.put(struct.pack('>Q', nonce))


def _worker(obj):
    q = multiprocessing.Queue()
    p = multiprocessing.Process(
        target=_pow_worker, args=(obj.pow_target(), obj.pow_initial_hash(), q))

    logging.debug('Starting POW process')
    t = time.time()
    p.start()
    nonce = q.get()
    p.join()

    logging.debug(
        'Finished doing POW, nonce: %s, time: %ss', nonce, time.time() - t)
    obj = structure.Object(
        nonce, obj.expires_time, obj.object_type, obj.version,
        obj.stream_number, obj.object_payload)
    logging.debug(
        'Object vector is %s', base64.b16encode(obj.vector).decode())

    with shared.objects_lock:
        shared.objects[obj.vector] = obj
        shared.vector_advertise_queue.put(obj.vector)


def do_pow_and_publish(obj):
    t = threading.Thread(target=_worker, args=(obj, ))
    t.start()
