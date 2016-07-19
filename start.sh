#!/bin/sh
cd "$(dirname "$0")"
git pull
python3 src/main.py
