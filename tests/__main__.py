from __future__ import absolute_import, print_function

import logging
import unittest

from lark import logger

from .test_cache import TestCache
from .test_grammar import TestGrammar
from .test_reconstructor import TestReconstructor
from .test_tools import TestStandalone
from .test_tree_forest_transformer import TestTreeForestTransformer
from .test_trees import TestTrees

try:
    from .test_nearley.test_nearley import TestNearley
except ImportError:
    logger.warning(
        "Warning: Skipping tests for Nearley grammar imports (js2py required)"
    )

# from .test_selectors import TestSelectors
# from .test_grammars import TestPythonG, TestConfigG

from .test_logger import Testlogger
from .test_parser import TestCykStandard  # TestFullEarleyStandard,
from .test_parser import (
    TestEarleyDynamic,
    TestEarleyStandard,
    TestFullEarleyDynamic,
    TestFullEarleyDynamic_complete,
    TestLalrContextual,
    TestLalrCustom,
    TestLalrStandard,
    TestParsers,
)

logger.setLevel(logging.INFO)

if __name__ == "__main__":
    unittest.main()
