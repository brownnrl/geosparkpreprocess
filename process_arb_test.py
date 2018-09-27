import unittest
from process_arb import parse_dms


class TestProcessArb(unittest.TestCase):

    def testDMS(self):
        self.assertAlmostEqual(parse_dms("35-46-00.0N"), 35.766666, places=4)
        self.assertAlmostEqual(parse_dms("35-46-00.0S"), -35.766666, places=4)
        self.assertAlmostEqual(parse_dms("108-13-00.0W"), -108.2166666, places=4)



