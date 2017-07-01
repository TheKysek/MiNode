import hashlib
import multiprocessing
import shared
import struct
import threading
import time

import structure


def _pow_worker(target, initial_hash, q):
    nonce = 0
    print("target: {}, initial_hash: {}".format(target, initial_hash.hex()))
    trial_value = target + 1

    while trial_value > target:
        nonce += 1
        trial_value = struct.unpack('>Q', hashlib.sha512(hashlib.sha512(struct.pack('>Q', nonce) + initial_hash).digest()).digest()[:8])[0]

    q.put(struct.pack('>Q', nonce))


def _worker(obj):
    q = multiprocessing.Queue()
    p = multiprocessing.Process(target=_pow_worker, args=(obj.pow_target(), obj.pow_initial_hash(), q))

    print("Starting POW process")
    t = time.time()
    p.start()
    nonce = q.get()
    p.join()
    print("Finished doing POW, nonce: {}, time: {}s".format(nonce, time.time() - t))

    obj = structure.Object(nonce, obj.expires_time, obj.object_type, obj.version, obj.stream_number, obj.object_payload)
    print("Object vector is {}".format(obj.vector.hex()))
    print("Advertising in 10s")
    time.sleep(10)
    print("shared.objects len: {}".format(len(shared.objects)))
    with shared.objects_lock:
        shared.objects[obj.vector] = obj
        shared.vector_advertise_queue.put(obj.vector)


def do_pow_and_publish(obj):
    t = threading.Thread(target=_worker, args=(obj, ))
    t.start()
