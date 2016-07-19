import threading
import time

import message
import shared


class Advertiser(threading.Thread):
    def __init__(self):
        super().__init__(name='Advertiser')

    def run(self):
        while True:
            time.sleep(0.4)
            self._advertise_vectors()
            self._advertise_addresses()

    @staticmethod
    def _advertise_vectors():
        vectors_to_advertise = set()
        while not shared.vector_advertise_queue.empty():
            vectors_to_advertise.add(shared.vector_advertise_queue.get())
        if len(vectors_to_advertise) > 0:
            for c in shared.connections.copy():
                if c.status == 'verack_received':
                    c.send_queue.put(message.Inv(vectors_to_advertise))

    @staticmethod
    def _advertise_addresses():
        addresses_to_advertise = set()
        while not shared.address_advertise_queue.empty():
            addresses_to_advertise.add(shared.address_advertise_queue.get())
        if len(addresses_to_advertise) > 0:
            for c in shared.connections.copy():
                if c.status == 'verack_received':
                    c.send_queue.put(message.Addr(addresses_to_advertise))
