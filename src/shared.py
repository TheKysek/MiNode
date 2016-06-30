# -*- coding: utf-8 -*-
import logging
import os
import queue
import threading

listening_port = 8444
data_directory = 'minode_data/'

log_level = logging.DEBUG

magic_bytes = b'\xe9\xbe\xb4\xd9'
protocol_version = 3
services = 1  # NODE_NETWORK
stream = 1
nonce = os.urandom(8)
user_agent = b'MiNode-v0.0.1'
timeout = 600
header_length = 24

nonce_trials_per_byte = 1000
payload_length_extra_bytes = 1000

# Longer synchronization, lower bandwidth usage, not really working
conserve_bandwidth = False
requested_objects = set()
requested_objects_lock = threading.Lock()

shutting_down = False

vector_advertise_queue = queue.Queue()
address_advertise_queue = queue.Queue()

connections = set()
connections_lock = threading.Lock()

hosts = set()

core_nodes = set()

node_pool = set()
unchecked_node_pool = set()

outgoing_connections = 8

objects = {}
objects_lock = threading.Lock()

