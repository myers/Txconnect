import os 

from twisted.trial.unittest import TestCase

from ..directconnect import filelist
            
class TestFilelist(TestCase):

    testFilelistPath = os.path.join(os.path.dirname(__file__), 'filelist.xml.bz2')
    def testFilelist(self):
        res = list(filelist.files(self.testFilelistPath, 'level1'))
        self.assertEqual(8, len(res))
        self.assertEqual(u'level1\\level2b\\level3b\\level3b-file2.jpg', res[-1][0])
        self.assertEqual(u'level2b/level3b/level3b-file2.jpg', res[-1][1])

    def testWalkFilelist(self):
        ii = iter(filelist.walk(self.testFilelistPath))
        root, dirs, files = ii.next()
        self.assertEqual(r'level1\level2a\level3a', root)
        self.assertEqual([], dirs)
        self.assertEqual([u'level3a-file1.txt', u'level3a-file2.txt', u'level3a-file3.txt'], [ff.basename() for ff in files])

        root, dirs, files = ii.next()
        self.assertEqual(r'level1\level2a', root)
        self.assertEqual(['level3a'], dirs)
        self.assertEqual(['level2a-file1.jpg', 'level2a-file2.jpg', 'level2a-file3.jpg'], [ff.basename() for ff in files])
 
        root, dirs, files = ii.next()
        self.assertEqual(r'level1\level2b\level3b', root)
        self.assertEqual([], dirs)
        self.assertEqual(['level3b-file1.jpg', 'level3b-file2.jpg'], [ff.basename() for ff in files])

        root, dirs, files = ii.next()
        self.assertEqual(r'level1\level2b', root)
        self.assertEqual(['level3b'], dirs)
        self.assertEqual([], [ff.basename() for ff in files])

        root, dirs, files = ii.next()
        self.assertEqual(r'level1', root)
        self.assertEqual(['level2a', 'level2b'], dirs)
        self.assertEqual([], [ff.basename() for ff in files])

        self.assertRaises(StopIteration, ii.next)