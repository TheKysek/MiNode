# -*- coding: utf-8 -*-
import base64
import logging
import os
import pickle
import queue
import random
import threading
import time

from . import pow, shared, structure
from .connection import Connection
from .i2p import I2PDialer


class Manager(threading.Thread):
    def __init__(self):
        super().__init__(name='Manager')
        self.q = queue.Queue()
        self.last_cleaned_objects = time.time()
        self.last_cleaned_connections = time.time()
        self.last_pickled_objects = time.time()
        self.last_pickled_nodes = time.time()
        # Publish destination 5-15 minutes after start
        self.last_published_i2p_destination = \
            time.time() - 50 * 60 + random.uniform(-1, 1) * 300

    def run(self):
        while True:
            time.sleep(0.8)
            now = time.time()
            if shared.shutting_down:
                logging.debug('Shutting down Manager')
                break
            if now - self.last_cleaned_objects > 90:
                self.clean_objects()
                self.last_cleaned_objects = now
            if now - self.last_cleaned_connections > 2:
                self.manage_connections()
                self.last_cleaned_connections = now
            if now - self.last_pickled_objects > 100:
                self.pickle_objects()
                self.last_pickled_objects = now
            if now - self.last_pickled_nodes > 60:
                self.pickle_nodes()
                self.last_pickled_nodes = now
            if now - self.last_published_i2p_destination > 3600:
                self.publish_i2p_destination()
                self.last_published_i2p_destination = now

    @staticmethod
    def clean_objects():
        for vector in set(shared.objects):
            if shared.objects[vector].is_expired():
                with shared.objects_lock:
                    del shared.objects[vector]
                logging.debug(
                    'Deleted expired object: %s',
                    base64.b16encode(vector).decode())

    @staticmethod
    def manage_connections():
        hosts = set()
        outgoing_connections = 0
        for c in shared.connections.copy():
            if not c.is_alive() or c.status == 'disconnected':
                with shared.connections_lock:
                    shared.connections.remove(c)
            else:
                hosts.add(c.host)
                if not c.server:
                    outgoing_connections += 1

        for d in shared.i2p_dialers.copy():
            hosts.add(d.destination)
            if not d.is_alive():
                shared.i2p_dialers.remove(d)

        to_connect = set()
        if shared.trusted_peer:
            to_connect.add(shared.trusted_peer)

        if (
            outgoing_connections < shared.outgoing_connections
            and shared.send_outgoing_connections and not shared.trusted_peer
        ):

            if shared.ip_enabled:
                if len(shared.unchecked_node_pool) > 16:
                    to_connect.update(random.sample(
                        shared.unchecked_node_pool, 16))
                else:
                    to_connect.update(shared.unchecked_node_pool)
                shared.unchecked_node_pool.difference_update(to_connect)
                if len(shared.node_pool) > 8:
                    to_connect.update(random.sample(shared.node_pool, 8))
                else:
                    to_connect.update(shared.node_pool)

            if shared.i2p_enabled:
                if len(shared.i2p_unchecked_node_pool) > 16:
                    to_connect.update(
                        random.sample(shared.i2p_unchecked_node_pool, 16))
                else:
                    to_connect.update(shared.i2p_unchecked_node_pool)
                shared.i2p_unchecked_node_pool.difference_update(to_connect)
                if len(shared.i2p_node_pool) > 8:
                    to_connect.update(random.sample(shared.i2p_node_pool, 8))
                else:
                    to_connect.update(shared.i2p_node_pool)

        for addr in to_connect:
            if addr[0] in hosts:
                continue
            if addr[1] == 'i2p' and shared.i2p_enabled:
                if shared.i2p_session_nick and addr[0] != shared.i2p_dest_pub:
                    try:
                        d = I2PDialer(
                            shared,
                            addr[0], shared.i2p_session_nick,
                            shared.i2p_sam_host, shared.i2p_sam_port)
                        d.start()
                        hosts.add(d.destination)
                        shared.i2p_dialers.add(d)
                    except Exception:
                        logging.warning(
                            'Exception while trying to establish'
                            ' an I2P connection', exc_info=True)
                else:
                    continue
            else:
                c = Connection(addr[0], addr[1])
                c.start()
                hosts.add(c.host)
                with shared.connections_lock:
                    shared.connections.add(c)
        shared.hosts = hosts

    @staticmethod
    def pickle_objects():
        try:
            with open(
                os.path.join(shared.data_directory, 'objects.pickle'), 'bw'
            ) as dst:
                with shared.objects_lock:
                    pickle.dump(shared.objects, dst, protocol=3)
                logging.debug('Saved objects')
        except Exception as e:
            logging.warning('Error while saving objects')
            logging.warning(e)

    @staticmethod
    def pickle_nodes():
        if len(shared.node_pool) > 10000:
            shared.node_pool = set(random.sample(shared.node_pool, 10000))
        if len(shared.unchecked_node_pool) > 1000:
            shared.unchecked_node_pool = set(
                random.sample(shared.unchecked_node_pool, 1000))

        if len(shared.i2p_node_pool) > 1000:
            shared.i2p_node_pool = set(
                random.sample(shared.i2p_node_pool, 1000))
        if len(shared.i2p_unchecked_node_pool) > 100:
            shared.i2p_unchecked_node_pool = set(
                random.sample(shared.i2p_unchecked_node_pool, 100))

        try:
            with open(
                os.path.join(shared.data_directory, 'nodes.pickle'), 'bw'
            ) as dst:
                pickle.dump(shared.node_pool, dst, protocol=3)
            with open(
                os.path.join(shared.data_directory, 'i2p_nodes.pickle'), 'bw'
            ) as dst:
                pickle.dump(shared.i2p_node_pool, dst, protocol=3)
                logging.debug('Saved nodes')
        except Exception:
            logging.warning('Error while saving nodes', exc_info=True)

    @staticmethod
    def publish_i2p_destination():
        if shared.i2p_session_nick and not shared.i2p_transient:
            logging.info('Publishing our I2P destination')
            dest_pub_raw = base64.b64decode(
                shared.i2p_dest_pub, altchars=b'-~')
            obj = structure.Object(
                b'\x00' * 8, int(time.time() + 2 * 3600),
                shared.i2p_dest_obj_type, shared.i2p_dest_obj_version,
                1, dest_pub_raw)
            pow.do_pow_and_publish(obj)
