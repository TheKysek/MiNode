import logging

from i2p.controller import I2PController
from i2p.listener import I2PListener

logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] [%(levelname)s] %(message)s')

i2p_controller = I2PController()

i2p_controller.start()

session_nick = i2p_controller.nick

i2p_listener = I2PListener(session_nick)
i2p_listener.start()
