#!/usr/bin/env python

import os

from setuptools import setup, find_packages

from minode import shared


README = open(os.path.join(
    os.path.abspath(os.path.dirname(__file__)), 'README.md')).read()

name, version = shared.user_agent.strip(b'/').split(b':')

setup(
    name=name.decode('utf-8'),
    version=version.decode('utf-8'),
    description='Python 3 implementation of the Bitmessage protocol.'
    ' Designed only to route objects inside the network.',
    long_description=README,
    license='MIT',
    author='Krzysztof Oziomek',
    url='https://github.com/g1itch/MiNode',
    packages=find_packages(),
    package_data={'': ['*.csv', 'tls/*.pem']},
    entry_points={'console_scripts': ['minode = minode.main:main']},
    classifiers=[
        "License :: OSI Approved :: MIT License"
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Topic :: Internet",
        "Topic :: Security :: Cryptography",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
