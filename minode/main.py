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
import i2p.controller
import i2p.listener
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
    parser.add_argument('--i2p', help='Enable I2P support (uses SAMv3)', action='store_true')
    parser.add_argument('--i2p-tunnel-length', help='Length of I2P tunnels', type=int)
    parser.add_argument('--i2p-sam-host', help='Host of I2P SAMv3 bridge')
    parser.add_argument('--i2p-sam-port', help='Port of I2P SAMv3 bridge', type=int)

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

    if shared.i2p_enabled:
        dest_priv = b''

        try:
            with open(shared.data_directory + 'i2p_dest_priv.key', mode='br') as file:
                dest_priv = file.read()
                logging.debug('Loaded I2P destination private key.')
        except Exception as e:
            logging.warning('Error while loading I2P destination private key.')
            logging.warning(e)

        logging.info('Starting I2P Controller and creating tunnels. This may take a while.')
        i2p_controller = i2p.controller.I2PController(shared.i2p_sam_host, shared.i2p_sam_port, dest_priv)
        i2p_controller.start()

        shared.i2p_dest_pub = i2p_controller.dest_pub
        shared.i2p_session_nick = i2p_controller.nick

        logging.info('Local I2P destination: {}'.format(shared.i2p_dest_pub.decode()))
        logging.info('I2P session nick: {}'.format(shared.i2p_session_nick.decode()))

        logging.info('Starting I2P Listener')
        i2p_listener = i2p.listener.I2PListener(i2p_controller.nick)
        i2p_listener.start()

        try:
            with open(shared.data_directory + 'i2p_dest_priv.key', mode='bw') as file:
                file.write(i2p_controller.dest_priv)
                logging.debug('Saved I2P destination private key.')
        except Exception as e:
            logging.warning('Error while saving I2P destination private key.')
            logging.warning(e)

        try:
            with open(shared.data_directory + 'i2p_dest.pub', mode='bw') as file:
                file.write(shared.i2p_dest_pub)
                logging.debug('Saved I2P destination public key.')
        except Exception as e:
            logging.warning('Error while saving I2P destination public key.')
            logging.warning(e)

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
