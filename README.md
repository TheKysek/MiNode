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
usage: main.py [-h] [-p PORT] [--debug] [--data-dir DATA_DIR] [--no-incoming]
               [--no-outgoing] [--trusted-peer TRUSTED_PEER]
               [--connection-limit CONNECTION_LIMIT]

optional arguments:
  -h, --help            show this help message and exit
  -p PORT, --port PORT  Port to listen on
  --debug               Enable debug logging
  --data-dir DATA_DIR   Path to data directory
  --no-incoming         Do not listen for incoming connections
  --no-outgoing         Do not send outgoing connections
  --trusted-peer TRUSTED_PEER
                        Specify a trusted peer we should connect to
  --connection-limit CONNECTION_LIMIT
                        Maximum number of connections
```

## Contact
- TheKysek: BM-2cVUMXVnQXmTJDmb7q1HUyEqkT92qjwGvJ

## Links
- [Bitmessage project website](https://bitmessage.org)
- [Protocol specification](https://bitmessage.org/wiki/Protocol_specification)
