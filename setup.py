#!/usr/bin/env python

import os

from setuptools import setup, find_packages


README = open(os.path.join(
    os.path.abspath(os.path.dirname(__file__)), 'README.md')).read()


setup(
    name='MiNode',
    version='0.3.0',
    description='Python 3 implementation of the Bitmessage protocol.'
    ' Designed only to route objects inside the network.',
    long_description=README,
    license='MIT',
    author='Krzysztof Oziomek',
    url='https://github.com/TheKysek/MiNode',
    packages=find_packages(),
    package_data={'': ['*.csv', 'tls/*.pem']},
    entry_points={'console_scripts': ['minode = minode.app:main']},
    classifiers=[
        "License :: OSI Approved :: MIT License"
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Topic :: Internet",
        "Topic :: Security :: Cryptography",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
