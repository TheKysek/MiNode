# -*- coding: utf-8 -*-
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


def main():
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
    logging.basicConfig(level=shared.log_level, format='[%(asctime)s] [%(levelname)s] %(message)s')
    logging.info('Starting MiNode')
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
                logging.warning('Error while starting IPv6 listener')
                logging.warning(e)

        try:
            listener_ipv4 = Listener('', shared.listening_port)
            listener_ipv4.start()
        except Exception as e:
            if listener_ipv6:
                logging.warning('Error while starting IPv4 listener. '
                                'However the IPv6 one seems to be working and will probably accept IPv4 connections.')
            else:
                logging.error('Error while starting IPv4 listener.'
                              'You will not receive incoming connections. Please check your port configuration')
                logging.error(e)

if __name__ == '__main__':
    main()
