import unittest

from .. import statsutil
class StatsutilCase(unittest.TestCase):
    def testSimple(self):
        wa = statsutil.WeightedAvg(5)
        self.assertEqual(1, wa.add(1))
        for ii in range(5): wa.add(0)
        self.assertEqual(0, wa.add(0))
        

if __name__ == '__main__':
    unittest.main()
