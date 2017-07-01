# MiNode
Python 3 implementation of the Bitmessage protocol. Designed only to route objects inside the network.

## Requirements
- python3 (or pypy3)
- openssl

## Running
```
git clone https://github.com/TheKysek/MiNode.git
```
```
cd MiNode
chmod +x start.sh
./start.sh
```

It is worth noting that the `start.sh` file MiNode no longer tries to do a `git pull` in order to update to the latest version.
Is is now done by the `update.sh` file.

## Command line
```
usage: main.py [-h] [-p PORT] [--host HOST] [--debug] [--data-dir DATA_DIR]
               [--no-incoming] [--no-outgoing] [--no-ip]
               [--trusted-peer TRUSTED_PEER]
               [--connection-limit CONNECTION_LIMIT] [--i2p]
               [--i2p-tunnel-length I2P_TUNNEL_LENGTH]
               [--i2p-sam-host I2P_SAM_HOST] [--i2p-sam-port I2P_SAM_PORT]

optional arguments:
  -h, --help            show this help message and exit
  -p PORT, --port PORT  Port to listen on
  --host HOST           Listening host
  --debug               Enable debug logging
  --data-dir DATA_DIR   Path to data directory
  --no-incoming         Do not listen for incoming connections
  --no-outgoing         Do not send outgoing connections
  --no-ip               Do not use IP network
  --trusted-peer TRUSTED_PEER
                        Specify a trusted peer we should connect to
  --connection-limit CONNECTION_LIMIT
                        Maximum number of connections
  --i2p                 Enable I2P support (uses SAMv3)
  --i2p-tunnel-length I2P_TUNNEL_LENGTH
                        Length of I2P tunnels
  --i2p-sam-host I2P_SAM_HOST
                        Host of I2P SAMv3 bridge
  --i2p-sam-port I2P_SAM_PORT
                        Port of I2P SAMv3 bridge

```
## I2P support
MiNode has support for connections over I2P network.
To use it it needs an I2P router with SAMv3 activated (both Java I2P and i2pd are supported).
Keep in mind that I2P connections are slow and full synchronization may take a while.
### Examples
Connect to both IP and I2P networks (SAM bridge on default host and port 127.0.0.1:7656) and set tunnel length to 2 (default is 3).
```
$ ./start.sh --i2p --i2p-tunnel-length 2
```

Connect only to I2P network and listen for IP connections only from local machine.
```
$ ./start.sh --i2p --no-ip --host 127.0.0.1
```
or
```
$ ./i2p_bridge.sh
```
If you add `trustedpeer = 127.0.0.1:8444` to `keys.dat` file in PyBitmessage it will allow you to use it anonymously over I2P with MiNode acting as a bridge.
## Contact
- TheKysek: BM-2cVUMXVnQXmTJDmb7q1HUyEqkT92qjwGvJ

## Links
- [Bitmessage project website](https://bitmessage.org)
- [Protocol specification](https://bitmessage.org/wiki/Protocol_specification)
