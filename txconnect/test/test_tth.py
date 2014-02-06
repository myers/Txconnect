import unittest, tempfile

from ..tth import TTH

class TTHTestCase(unittest.TestCase):
    leaves = '=\xd0D\xc3\xd5\xfcXR\x87\xe1\x8e\x8av\x05\x8eW\xba\x83\xf4k\xa9;\xeb3=\xd0D\xc3\xd5\xfcXR\x87\xe1\x8e\x8av\x05\x8eW\xba\x83\xf4k\xa9;\xeb3\xc3\xc1\x86Q~b3\x1d_|B\x92\xe6\xfam\xd2\x9f\x87\xb4\x9fA\xcc\xfd2'
    largerLeaves = '_\x1a\x0b\x942\xcb\x14NuwIZ\x93\xb4\xc4\xc9\x98\xe6u|IP]\xdb_\x1a\x0b\x942\xcb\x14NuwIZ\x93\xb4\xc4\xc9\x98\xe6u|IP]\xdb_\x1a\x0b\x942\xcb\x14NuwIZ\x93\xb4\xc4\xc9\x98\xe6u|IP]\xdb=\xd0D\xc3\xd5\xfcXR\x87\xe1\x8e\x8av\x05\x8eW\xba\x83\xf4k\xa9;\xeb3'
    
    def testWithLeaves(self):
        tth = TTH(root='LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI', leaves=self.leaves, fileSize=10240)
        self.assertEqual(5, tth.computeLevels())
        self.assertEqual(16384, tth.blockSize(0))
        self.assertEqual(8192, tth.blockSize(1))
        self.assertEqual(4096, tth.blockSize(2))
        self.assertEqual(2048, tth.blockSize(3))
        self.assertEqual(1024, tth.blockSize(4))

        self.assertEqual(4096, tth.blockSize())
        

    def testBlocksNeeded(self):
        fileSize = 10240
        tf = tempfile.NamedTemporaryFile('r+b')
        tf.truncate(fileSize)
        tf.flush()
    
        tth = TTH(fileName=tf.name, root='LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI', leaves=self.leaves, fileSize=fileSize)
        self.assertEqual(5, tth.computeLevels())
        self.assertEqual(4096, tth.blockSize())
        blocksNeeded = tth.blocksNeeded()
        self.assertEqual(3, len(blocksNeeded))
        self.assertEqual((0, 4096,), blocksNeeded[0])
        self.assertEqual((4096, 4096,), blocksNeeded[1])
        self.assertEqual((8192, 2048,), blocksNeeded[2])
        self.assertEqual(fileSize, sum([aa[1] for aa in blocksNeeded]))
        
        tf.seek(0)
        tf.write('a'*4096)
        tf.flush()
        blocksNeeded = tth.blocksNeeded()
        self.assertEqual(2, len(blocksNeeded))
        self.assertEqual((4096, 4096,), blocksNeeded[0])
        self.assertEqual((8192, 2048,), blocksNeeded[1])

        tf.write('a'*4096)
        tf.flush()
        blocksNeeded = tth.blocksNeeded()
        self.assertEqual(1, len(blocksNeeded))
        self.assertEqual((8192, 2048,), blocksNeeded[0])

        tf.write('a'*2048)
        tf.flush()
        blocksNeeded = tth.blocksNeeded()
        self.assertEqual(0, len(blocksNeeded))
        
        tf.close()

    def testBlocksNeededWithLargerFile(self):
        fileSize = 102400
        tf = tempfile.NamedTemporaryFile('r+b')
        tf.truncate(fileSize)
        tf.flush()
    
        tth = TTH(fileName=tf.name, root='43VWWPPTUQZGGADKNAX25V4LBH3P4AGEJRALWIA', leaves=self.largerLeaves, fileSize=102400)
        self.assertEqual(8, tth.computeLevels())
        self.assertEqual(32768, tth.blockSize())
        blocksNeeded = tth.blocksNeeded()
        self.assertEqual(fileSize, sum([aa[1] for aa in blocksNeeded]))
        self.assertEqual(4, len(blocksNeeded))

        tf.seek(blocksNeeded[2][0])
        tf.write('a'*tth.blockSize())
        tf.flush()

        blocksNeeded = tth.blocksNeeded()
        self.assertEqual(3, len(blocksNeeded))

        tf.close()

    def testWithFile(self):
        tf = tempfile.NamedTemporaryFile('r+b')
        tf.write('a'*10240)
        tf.flush()
        tth = TTH(tf.name)
        self.assertEqual(tth.getroot(), 'LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI')
        self.assertEqual(''.join(tth.gettree()[2]), self.leaves)
        
        tf.close()

    def testWithBadRoot(self):
        def _():
            TTH(root='XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX', leaves=self.leaves, fileSize=10240)
        self.assertRaises(ValueError, _)

    def testWithBadLeaves(self):
        def _():
            TTH(root='LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI', leaves=self.leaves + 'X', fileSize=10240)
        self.assertRaises(ValueError, _)

    # test vectors from http://web.archive.org/web/20080316033726/http://www.open-content.net/specs/draft-jchapweske-thex-02.html#choice_of_segment_size    
    def testWithZeroByte(self):
        tf = tempfile.NamedTemporaryFile()
        tth = TTH(tf.name)
        self.assertEqual(tth.getroot(), 'LWPNACQDBZRYXW3VHJVCJ64QBZNGHOHHHZWCLNQ')
        tf.close()

    def testWithOneNull(self):
        tf = tempfile.NamedTemporaryFile()
        tf.write('\0')
        tf.flush()
        tth = TTH(tf.name)
        self.assertEqual(tth.getroot(), 'VK54ZIEEVTWNAUI5D5RDFIL37LX2IQNSTAXFKSA')
        tf.close()

    def testWith1024As(self):
        tf = tempfile.NamedTemporaryFile()
        tf.write('A'*1024)
        tf.flush()
        tth = TTH(tf.name)
        self.assertEqual(tth.getroot(), 'L66Q4YVNAFWVS23X2HJIRA5ZJ7WXR3F26RSASFA')
        tf.close()
        
    def testWith1025As(self):
        tf = tempfile.NamedTemporaryFile()
        tf.write('A'*1025)
        tf.flush()
        tth = TTH(tf.name)
        self.assertEqual(tth.getroot(), 'PZMRYHGY6LTBEH63ZWAHDORHSYTLO4LEFUIKHWY')
        tf.close()

    def test_getleaves(self):
        tf = tempfile.NamedTemporaryFile()
        tf.write('a'*102400)
        tf.flush()
        tth = TTH(tf.name)
        self.assertEqual(tth.getleaves(32768), self.largerLeaves)
        tf.close()

    def test_getleaves_forZeroSizeFile(self):
        tf = tempfile.NamedTemporaryFile()
        tf.write('a'*0)
        tf.flush()
        tth = TTH(tf.name)
        self.assertEquals('', tth.getleaves(1024))
        tf.close()

    def test_blocksNeeded_for_file_that_does_not_exists(self):
        fileSize = 10240
        tth = TTH(fileName=tempfile.mktemp(), root='LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI', leaves=self.leaves, fileSize=fileSize)
        blocksNeeded = tth.blocksNeeded()
        self.assertEqual(3, len(blocksNeeded))
        self.assertEqual((0, 4096,), blocksNeeded[0])
        self.assertEqual((4096, 4096,), blocksNeeded[1])
        self.assertEqual((8192, 2048,), blocksNeeded[2])
        self.assertEqual(fileSize, sum([aa[1] for aa in blocksNeeded]))
    

if __name__ == '__main__':
    unittest.main()
