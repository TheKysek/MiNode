# -*- coding: utf-8 -*-
import base64
import logging
import pickle
import queue
import random
import threading
import time

from connection import Connection
import shared


class Manager(threading.Thread):
    def __init__(self):
        super().__init__(name='Manager')
        self.q = queue.Queue()
        self.last_cleaned_objects = time.time()
        self.last_cleaned_connections = time.time()
        self.last_pickled_objects = time.time()
        self.last_pickled_nodes = time.time()

    def run(self):
        while True:
            time.sleep(0.8)
            now = time.time()
            if now - self.last_cleaned_objects > 90:
                self.clean_objects()
                self.last_cleaned_objects = now
            if now - self.last_cleaned_connections > 2:
                self.clean_connections()
                self.last_cleaned_connections = now
            if now - self.last_pickled_objects > 100:
                self.pickle_objects()
                self.last_pickled_objects = now
            if now - self.last_pickled_nodes > 60:
                self.pickle_nodes()
                self.last_pickled_nodes = now

            if shared.shutting_down:
                logging.debug('Shutting down connections')
                self.shutdown_connections()
                logging.debug('Shutting down Manager')
                break

    @staticmethod
    def clean_objects():
        for vector in set(shared.objects):
            if shared.objects[vector].is_expired():
                with shared.objects_lock:
                    del shared.objects[vector]
                logging.debug('Deleted expired object: {}'.format(base64.b16encode(vector).decode()))

    @staticmethod
    def clean_connections():
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
        if outgoing_connections < shared.outgoing_connections and shared.send_outgoing_connections:
            to_connect = set()
            if len(shared.unchecked_node_pool) > 16:
                to_connect.update(random.sample(shared.unchecked_node_pool, 16))
            else:
                to_connect.update(shared.unchecked_node_pool)
            shared.unchecked_node_pool.difference_update(to_connect)
            if len(shared.node_pool) > 8:
                to_connect.update(random.sample(shared.node_pool, 8))
            else:
                to_connect.update(shared.node_pool)
            for addr in to_connect:
                if addr[0] in hosts:
                    continue
                c = Connection(addr[0], addr[1])
                c.start()
                hosts.add(c.host)
                with shared.connections_lock:
                    shared.connections.add(c)
        shared.hosts = hosts

    @staticmethod
    def shutdown_connections():
        for c in shared.connections.copy():
            c.send_queue.put(None)

    @staticmethod
    def pickle_objects():
        try:
            with open(shared.data_directory + 'objects.pickle', mode='bw') as file:
                with shared.objects_lock:
                    pickle.dump(shared.objects, file, protocol=3)
                logging.debug('Saved objects')
        except Exception as e:
            logging.warning('Error while saving objects')
            logging.warning(e)

    @staticmethod
    def pickle_nodes():
        if len(shared.node_pool) > 10000:
            shared.node_pool = set(random.sample(shared.node_pool, 10000))
        if len(shared.unchecked_node_pool) > 1000:
            shared.unchecked_node_pool = set(random.sample(shared.unchecked_node_pool, 1000))
        try:
            with open(shared.data_directory + 'nodes.pickle', mode='bw') as file:
                pickle.dump(shared.node_pool, file, protocol=3)
                logging.debug('Saved nodes')
        except Exception as e:
            logging.warning('Error while saving nodes')
            logging.warning(e)
