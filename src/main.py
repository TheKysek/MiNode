# -*- coding: utf-8 -*-
import csv
import logging
import pickle
import socket

from advertiser import Advertiser
from manager import Manager
from listener import Listener
import shared


def main():
    logging.basicConfig(level=shared.log_level, format='[%(asctime)s] [%(levelname)s] %(message)s')
    logging.info('Starting MiNode')
    try:
        with open(shared.data_directory + 'objects.pickle', mode='br') as file:
            shared.objects = pickle.load(file)
    except Exception as e:
        logging.warning('Error while loading objects from disk.')
        logging.warning(e)

    try:
        with open(shared.data_directory + 'nodes.pickle', mode='br') as file:
            shared.nodes = pickle.load(file)
    except Exception as e:
        logging.warning('Error while loading nodes from disk.')
        logging.warning(e)

    with open('core_nodes.csv', mode='r', newline='') as f:
        reader = csv.reader(f)
        shared.core_nodes = {tuple(row) for row in reader}
        shared.node_pool.update(shared.core_nodes)

    try:
        for item in socket.getaddrinfo('bootstrap8080.bitmessage.org', 80):
            shared.unchecked_node_pool.add((item[4][0], 8444))
            shared.unchecked_node_pool.add((item[4][0], 8080))
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

    try:
        listener_ipv4 = Listener('0.0.0.0', shared.listening_port)
        listener_ipv4.start()
    except Exception as e:
        logging.error('Error while starting IPv4 listener')
        logging.error(e)

    try:
        listener_ipv6 = Listener('::', shared.listening_port, family=socket.AF_INET6)
        listener_ipv6.start()
    except Exception as e:
        logging.error('Error while starting IPv6 listener')
        logging.error(e)

if __name__ == '__main__':
    main()
