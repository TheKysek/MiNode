# -*- coding: utf-8 -*-
import argparse
import csv
import logging
import os
import pickle
import signal
import socket

from advertiser import Advertiser
from manager import Manager
from listener import Listener
import shared


def handler(s, f):
    logging.info('Gracefully shutting down MiNode')
    shared.shutting_down = True


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', help='Port to listen on', type=int)
    parser.add_argument('--debug', help='Enable debug logging', action='store_true')
    parser.add_argument('--data-dir', help='Path to data directory')
    parser.add_argument('--no-incoming', help='Do not listen for incoming connections', action='store_true')
    parser.add_argument('--no-outgoing', help='Do not send outgoing connections', action='store_true')
    parser.add_argument('--trusted-peer', help='Specify a trusted peer we should connect to')
    parser.add_argument('--connection-limit', help='Maximum number of connections', type=int)

    args = parser.parse_args()
    if args.port:
        shared.listening_port = args.port
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
    if args.trusted_peer:
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


def main():
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    parse_arguments()

    logging.basicConfig(level=shared.log_level, format='[%(asctime)s] [%(levelname)s] %(message)s')
    logging.info('Starting MiNode')
    logging.info('Data directory: {}'.format(shared.data_directory))
    if not os.path.exists(shared.data_directory):
        try:
            os.makedirs(shared.data_directory)
        except Exception as e:
            logging.warning('Error while creating data directory in: {}'.format(shared.data_directory))
            logging.warning(e)
    try:
        with open(shared.data_directory + 'objects.pickle', mode='br') as file:
            shared.objects = pickle.load(file)
    except Exception as e:
        logging.warning('Error while loading objects from disk.')
        logging.warning(e)

    try:
        with open(shared.data_directory + 'nodes.pickle', mode='br') as file:
            shared.node_pool = pickle.load(file)
    except Exception as e:
        logging.warning('Error while loading nodes from disk.')
        logging.warning(e)

    with open(os.path.join(shared.source_directory, 'core_nodes.csv'), mode='r', newline='') as f:
        reader = csv.reader(f)
        shared.core_nodes = {tuple(row) for row in reader}
        shared.node_pool.update(shared.core_nodes)

    if not shared.trusted_peer:
        try:
            for item in socket.getaddrinfo('bootstrap8080.bitmessage.org', 80):
                shared.unchecked_node_pool.add((item[4][0], 8080))
                logging.debug('Adding ' + item[4][0] + ' to unchecked_node_pool based on DNS bootstrap method')
            for item in socket.getaddrinfo('bootstrap8444.bitmessage.org', 80):
                shared.unchecked_node_pool.add((item[4][0], 8444))
                logging.debug('Adding ' + item[4][0] + ' to unchecked_node_pool based on DNS bootstrap method')
        except Exception as e:
            logging.error('Error during DNS bootstrap')
            logging.error(e)

    manager = Manager()
    manager.clean_objects()
    manager.clean_connections()
    manager.start()

    advertiser = Advertiser()
    advertiser.start()

    listener_ipv4 = None
    listener_ipv6 = None

    if shared.listen_for_connections:
        if socket.has_ipv6:
            try:
                listener_ipv6 = Listener('', shared.listening_port, family=socket.AF_INET6)
                listener_ipv6.start()
            except Exception as e:
                logging.warning('Error while starting IPv6 listener on port {}'.format(shared.listening_port))
                logging.warning(e)

        try:
            listener_ipv4 = Listener('', shared.listening_port)
            listener_ipv4.start()
        except Exception as e:
            if listener_ipv6:
                logging.warning('Error while starting IPv4 listener on port {}. '.format(shared.listening_port) +
                                'However the IPv6 one seems to be working and will probably accept IPv4 connections.')
            else:
                logging.error('Error while starting IPv4 listener on port {}. '.format(shared.listening_port) +
                              'You will not receive incoming connections. Please check your port configuration')
                logging.error(e)

if __name__ == '__main__':
    main()
