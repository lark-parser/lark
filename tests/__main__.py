from __future__ import absolute_import, print_function

import unittest
import logging

from .test_trees import TestTrees

from .test_nearley.test_nearley import TestNearley

# from .test_selectors import TestSelectors
# from .test_grammars import TestPythonG, TestConfigG

from .test_parser import (
        TestLalrStandard,
        TestEarleyStandard,
        TestLalrContextual,
        TestEarleyScanless,
        TestEarleyDynamic,

        TestFullEarleyScanless,
        TestFullEarleyDynamic,

        TestParsers,
        )

logging.basicConfig(level=logging.INFO)

if __name__ == '__main__':
    unittest.main()
