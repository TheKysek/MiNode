# -*- coding: utf-8 -*-
import argparse
import base64
import csv
import logging
import multiprocessing
import os
import pickle
import signal
import socket

from . import i2p, shared
from .advertiser import Advertiser
from .manager import Manager
from .listener import Listener


def handler(s, f):
    logging.info('Gracefully shutting down MiNode')
    shared.shutting_down = True


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', help='Port to listen on', type=int)
    parser.add_argument('--host', help='Listening host')
    parser.add_argument(
        '--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--data-dir', help='Path to data directory')
    parser.add_argument(
        '--no-incoming', action='store_true',
        help='Do not listen for incoming connections')
    parser.add_argument(
        '--no-outgoing', action='store_true',
        help='Do not send outgoing connections')
    parser.add_argument(
        '--no-ip', action='store_true', help='Do not use IP network')
    parser.add_argument(
        '--trusted-peer', help='Specify a trusted peer we should connect to')
    parser.add_argument(
        '--connection-limit', type=int, help='Maximum number of connections')
    parser.add_argument(
        '--i2p', action='store_true', help='Enable I2P support (uses SAMv3)')
    parser.add_argument(
        '--i2p-tunnel-length', type=int, help='Length of I2P tunnels')
    parser.add_argument(
        '--i2p-sam-host', help='Host of I2P SAMv3 bridge')
    parser.add_argument(
        '--i2p-sam-port', type=int, help='Port of I2P SAMv3 bridge')
    parser.add_argument(
        '--i2p-transient', action='store_true',
        help='Generate new I2P destination on start')

    args = parser.parse_args()
    if args.port:
        shared.listening_port = args.port
    if args.host:
        shared.listening_host = args.host
    if args.debug:
        shared.log_level = logging.DEBUG
    if args.data_dir:
        dir_path = args.data_dir
        if not dir_path.endswith('/'):
            dir_path += '/'
        shared.data_directory = dir_path
    if args.no_incoming:
        shared.listen_for_connections = False
    if args.no_outgoing:
        shared.send_outgoing_connections = False
    if args.no_ip:
        shared.ip_enabled = False
    if args.trusted_peer:
        if len(args.trusted_peer) > 50:
            # I2P
            shared.trusted_peer = (args.trusted_peer.encode(), 'i2p')
        else:
            colon_count = args.trusted_peer.count(':')
            if colon_count == 0:
                shared.trusted_peer = (args.trusted_peer, 8444)
            if colon_count == 1:
                addr = args.trusted_peer.split(':')
                shared.trusted_peer = (addr[0], int(addr[1]))
            if colon_count >= 2:
                # IPv6 <3
                addr = args.trusted_peer.split(']:')
                addr[0] = addr[0][1:]
                shared.trusted_peer = (addr[0], int(addr[1]))
    if args.connection_limit:
        shared.connection_limit = args.connection_limit
    if args.i2p:
        shared.i2p_enabled = True
    if args.i2p_tunnel_length:
        shared.i2p_tunnel_length = args.i2p_tunnel_length
    if args.i2p_sam_host:
        shared.i2p_sam_host = args.i2p_sam_host
    if args.i2p_sam_port:
        shared.i2p_sam_port = args.i2p_sam_port
    if args.i2p_transient:
        shared.i2p_transient = True


def load_data():
    try:
        with open(
            os.path.join(shared.data_directory, 'objects.pickle'), 'br'
        ) as src:
            shared.objects = pickle.load(src)
    except Exception as e:
        logging.warning('Error while loading objects from disk.')
        logging.warning(e)

    try:
        with open(
            os.path.join(shared.data_directory, 'nodes.pickle'), 'br'
        ) as src:
            shared.node_pool = pickle.load(src)
    except Exception as e:
        logging.warning('Error while loading nodes from disk.')
        logging.warning(e)

    try:
        with open(
            os.path.join(shared.data_directory, 'i2p_nodes.pickle'), 'br'
        ) as src:
            shared.i2p_node_pool = pickle.load(src)
    except Exception as e:
        logging.warning('Error while loading nodes from disk.')
        logging.warning(e)

    with open(
        os.path.join(shared.source_directory, 'core_nodes.csv'),
        'r', newline=''
    ) as src:
        reader = csv.reader(src)
        shared.core_nodes = {tuple(row) for row in reader}
        shared.node_pool.update(shared.core_nodes)

    with open(
        os.path.join(shared.source_directory, 'i2p_core_nodes.csv'),
        'r', newline=''
    ) as f:
        reader = csv.reader(f)
        shared.i2p_core_nodes = {(row[0].encode(), 'i2p') for row in reader}
        shared.i2p_node_pool.update(shared.i2p_core_nodes)


def bootstrap_from_dns():
    try:
        for item in socket.getaddrinfo('bootstrap8080.bitmessage.org', 80):
            shared.unchecked_node_pool.add((item[4][0], 8080))
            logging.debug(
                'Adding %s to unchecked_node_pool'
                ' based on DNS bootstrap method', item[4][0])
        for item in socket.getaddrinfo('bootstrap8444.bitmessage.org', 80):
            shared.unchecked_node_pool.add((item[4][0], 8444))
            logging.debug(
                'Adding %s to unchecked_node_pool'
                ' based on DNS bootstrap method', item[4][0])
    except Exception:
        logging.error('Error during DNS bootstrap', exc_info=True)


def start_ip_listener():
    listener_ipv4 = None
    listener_ipv6 = None

    if socket.has_ipv6:
        try:
            listener_ipv6 = Listener(
                shared.listening_host,
                shared.listening_port, family=socket.AF_INET6)
            listener_ipv6.start()
        except Exception:
            logging.warning(
                'Error while starting IPv6 listener on port %s',
                shared.listening_port, exc_info=True)

    try:
        listener_ipv4 = Listener(shared.listening_host, shared.listening_port)
        listener_ipv4.start()
    except Exception:
        if listener_ipv6:
            logging.warning(
                'Error while starting IPv4 listener on port %s.'
                ' However the IPv6 one seems to be working'
                ' and will probably accept IPv4 connections.',
                shared.listening_port)
        else:
            logging.error(
                'Error while starting IPv4 listener on port %s.'
                'You will not receive incoming connections.'
                ' Please check your port configuration',
                shared.listening_port, exc_info=True)


def start_i2p_listener():
    # Grab I2P destinations from old object file
    for obj in shared.objects.values():
        if obj.object_type == shared.i2p_dest_obj_type:
            shared.i2p_unchecked_node_pool.add((
                base64.b64encode(obj.object_payload, altchars=b'-~'), 'i2p'))

    dest_priv = b''

    if not shared.i2p_transient:
        try:
            with open(
                os.path.join(shared.data_directory, 'i2p_dest_priv.key'), 'br'
            ) as src:
                dest_priv = src.read()
                logging.debug('Loaded I2P destination private key.')
        except Exception:
            logging.warning(
                'Error while loading I2P destination private key.',
                exc_info=True)

    logging.info(
        'Starting I2P Controller and creating tunnels. This may take a while.')
    i2p_controller = i2p.I2PController(
        shared, shared.i2p_sam_host, shared.i2p_sam_port, dest_priv)
    i2p_controller.start()

    shared.i2p_dest_pub = i2p_controller.dest_pub
    shared.i2p_session_nick = i2p_controller.nick

    logging.info('Local I2P destination: %s', shared.i2p_dest_pub.decode())
    logging.info('I2P session nick: %s', shared.i2p_session_nick.decode())

    logging.info('Starting I2P Listener')
    i2p_listener = i2p.I2PListener(shared, i2p_controller.nick)
    i2p_listener.start()

    if not shared.i2p_transient:
        try:
            with open(
                os.path.join(shared.data_directory, 'i2p_dest_priv.key'), 'bw'
            ) as src:
                src.write(i2p_controller.dest_priv)
                logging.debug('Saved I2P destination private key.')
        except Exception:
            logging.warning(
                'Error while saving I2P destination private key.',
                exc_info=True)

    try:
        with open(
            os.path.join(shared.data_directory, 'i2p_dest.pub'), 'bw'
        ) as src:
            src.write(shared.i2p_dest_pub)
            logging.debug('Saved I2P destination public key.')
    except Exception:
        logging.warning(
            'Error while saving I2P destination public key.', exc_info=True)


def main():
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    parse_arguments()

    logging.basicConfig(
        level=shared.log_level,
        format='[%(asctime)s] [%(levelname)s] %(message)s')
    logging.info('Starting MiNode')

    logging.info('Data directory: %s', shared.data_directory)
    if not os.path.exists(shared.data_directory):
        try:
            os.makedirs(shared.data_directory)
        except Exception:
            logging.warning(
                'Error while creating data directory in: %s',
                shared.data_directory, exc_info=True)

    load_data()

    if shared.ip_enabled and not shared.trusted_peer:
        bootstrap_from_dns()

    if shared.i2p_enabled:
        # We are starting it before cleaning expired objects
        # so we can collect I2P destination objects
        start_i2p_listener()

    for vector in set(shared.objects):
        if not shared.objects[vector].is_valid():
            if shared.objects[vector].is_expired():
                logging.debug(
                    'Deleted expired object: %s',
                    base64.b16encode(vector).decode())
            else:
                logging.warning(
                    'Deleted invalid object: %s',
                    base64.b16encode(vector).decode())
            del shared.objects[vector]

    manager = Manager()
    manager.start()

    advertiser = Advertiser()
    advertiser.start()

    if shared.listen_for_connections:
        start_ip_listener()


if __name__ == '__main__':
    multiprocessing.set_start_method('spawn')
    main()
