#!/usr/bin/env python
"""Custom tests runner script"""
import random  # noseq
import sys
import unittest


def unittest_discover():
    """Explicit test suite creation"""
    loader = unittest.defaultTestLoader
    # randomize the order of tests in test cases
    loader.sortTestMethodsUsing = lambda a, b: random.randint(-1, 1)
    return loader.discover('minode.tests')


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest_discover())
    sys.exit(not result.wasSuccessful())
