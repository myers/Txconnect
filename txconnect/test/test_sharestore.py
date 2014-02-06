# -*- coding: utf8 -*-
import os, shutil, ntpath, time, glob

from twisted.trial.unittest import TestCase
from twisted.python import log, components
from twisted.python.filepath import FilePath
from twisted.internet import defer
import louie

from ..directconnect import filelist, interfaces

from .. import sharestore, dbthread, extutils

class StubConfig(dict):
    dataDir = ''

class ShareStoreTest(TestCase):
    @defer.inlineCallbacks
    def setUp(self):
        dbthread.setup()
        os.mkdir('foo')
        os.mkdir('bar')
        locator = components.Componentized()
        config = StubConfig(files=dict(shared=dict({'Foo': 'foo', 'Bar': 'bar'})))
        config.dataDir = FilePath(os.getcwd())
        locator.setComponent(interfaces.IConfig, config)
        self.extutilsService = extutils.ExtUtilsService()
        self.extutilsService.startService()
        locator.setComponent(interfaces.IHasher, self.extutilsService)
        locator.setComponent(interfaces.IDirLister, self.extutilsService)
        self.shareStore = sharestore.ShareStore(locator)
        self.shareStore.setupDone.addErrback(log.err)
        self.shareStore.startService()
        yield self.shareStore.setupDone

    @defer.inlineCallbacks
    def tearDown(self):
        yield self.shareStore.stopService()
        yield self.extutilsService.stopService()
        yield dbthread.thread.shutdown()
        shutil.rmtree('foo')
        shutil.rmtree('bar')
        for fn in glob.glob('*.sqlite3'):
            os.unlink(fn)
            
    def _makeFile(self, path, size=10240, char='a'):
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        ff = open(path, 'w')
        ff.write(char*size)
        ff.close()
    
    def testIndexing(self):
        self._makeFile('foo/foo.txt')
        dd = self.shareStore.startIndexer()
        def _searchForFile(res):
            dd = self.shareStore.search('foo.txt')
            return dd.addCallback(_checkResults)
        def _checkResults(res):
            self.assertEqual(u'Foo\\foo.txt', res[0][0])

            # because the time resolution is at a second, if we change too soon we'll not notice the change
            time.sleep(1)
            os.unlink('foo/foo.txt')
            self._makeFile('bar/foo.txt')
            
            dd = self.shareStore.startIndexer()
            return dd.addCallback(_searchForFile2)
        def _searchForFile2(res):
            dd = self.shareStore.search('foo.txt')
            return dd.addCallback(_checkResults2)
        def _checkResults2(res):
            self.assertEqual(u'Bar\\foo.txt', res[0][0])
        return dd.addCallback(_searchForFile)

    def testAddFileToShare(self):
        self._makeFile('foo/foo.txt')
        dd = self.shareStore.add(FilePath('foo/foo.txt'))
        def _doSearch(path):
            dd = self.shareStore.search('foo')
            return dd.addCallback(_checkSearch)
        def _checkSearch(res):
            self.assertEquals(2, len(res))
            self.assertEquals((u'Foo', None, None), res[0])
            self.assertEquals((u'Foo\\foo.txt', 10240, u'LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI'), res[1])
        return dd.addCallback(_doSearch)

    def testAddBadlyEncodedFilenameToShare(self):
        badpath = u'foo/füo.txt'.encode('cp1252')
        self._makeFile(badpath)
        dd = self.shareStore.add(FilePath(badpath))
        def _doSearch(path):
            dd = self.shareStore.search(u'füo')
            return dd.addCallback(_checkSearch)
        def _checkSearch(res):
            self.assertEquals(0, len(res))
        return dd.addCallback(_doSearch)

    @defer.inlineCallbacks
    def testIgnoreBadlyEncodedFilenameWhileIndexing(self):
        badpath = u'foo/füo.txt'.encode('cp1252')
        self._makeFile(badpath)
        yield self.shareStore.startIndexer()

    def testAddEncodedFilenameToShare(self):
        badpath = u'foo/füo.txt'.encode('utf8')
        self._makeFile(badpath)
        dd = self.shareStore.add(FilePath(badpath))
        def _doSearch(path):
            dd = self.shareStore.search(u'füo')
            return dd.addCallback(_checkSearch)
        def _checkSearch(res):
            self.assertEquals(1, len(res))
        return dd.addCallback(_doSearch)

    def testFileTypes(self):
        """
        (2, u'Audio'),
        (3, u'Compressed'),   
        (4, u'Document'),
        (5, u'Executable'),
        (6, u'Picture'),
        (7, u'Video'),
        (8, u'Directory'),
        """
        self._makeFile('foo/two.mp3')
        self._makeFile('foo/three.rar', char='b')
        self._makeFile('foo/four.txt', char='c')
        self._makeFile('foo/five.exe', char='d')
        self._makeFile('foo/six.jpg', char='e')
        self._makeFile('foo/seven.avi', char='f')
        dd = self.shareStore.startIndexer()
        def _doSearch(res, name, filetype):
            assert isinstance(filetype, int)
            assert isinstance(name, basestring)
            dd = self.shareStore.search('foo', filetype=filetype)
            return dd.addCallback(_checkSearch, name, filetype)
        def _checkSearch(res, name, filetype):
            assert isinstance(filetype, int)
            assert isinstance(name, basestring)
            self.assertEquals(1, len(res), "I searched for filetype %r and got %r" % (filetype, res,))
            self.assertEquals(name, ntpath.splitext(ntpath.basename(res[0][0]))[0])
        dd.addCallback(_doSearch, 'two', 2)
        dd.addCallback(_doSearch, 'three', 3)
        dd.addCallback(_doSearch, 'four', 4)
        dd.addCallback(_doSearch, 'five', 5)
        dd.addCallback(_doSearch, 'six', 6)
        dd.addCallback(_doSearch, 'seven', 7)
        return dd.addCallback(_doSearch, 'Foo', 8)
        
    def test_getByPath(self):
        self._makeFile('foo/foo.txt')
        dd = self.shareStore.add(FilePath('foo/foo.txt'))
        def _getByPath(res):
            dd = self.shareStore.getByPath(u'Foo\\foo.txt')
            return dd.addCallback(_checkResults)
        def _checkResults(nfo):
            self.assertEqual(nfo['length'], 10240)
            self.assertEqual(nfo['tth'], u'LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI')
            self.assertEqual(nfo['dcPath'], u'Foo\\foo.txt')
            self.assertEqual(type(nfo['fileobj']), file)
        return dd.addCallback(_getByPath)
        
    def test_getByTTH(self):
        self._makeFile('foo/foo.txt')
        dd = self.shareStore.add(FilePath('foo/foo.txt'))
        def _getByTTH(res):
            dd = self.shareStore.getByTTH(u'LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI')
            return dd.addCallback(_checkResults)
        def _checkResults(nfo):
            self.assertEqual(nfo['length'], 10240)
            self.assertEqual(nfo['tth'], u'LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI')
            self.assertEqual(nfo['dcPath'], u'Foo\\foo.txt')
            self.assertEqual(type(nfo['fileobj']), file)
        return dd.addCallback(_getByTTH)

    def test_getLeavesForTTH(self):
        self._makeFile('foo/foo.txt', size=((2**20)*2+50))
        dd = self.shareStore.add(FilePath('foo/foo.txt'))
        def _getLeavesForTTH(res):
            dd = self.shareStore.getLeavesForTTH(u'3RDFCYVE6YU4JJQU6UXKNXSKZDG3A7KHC6L6PMA')
            return dd.addCallback(_checkResults)
        def _checkResults(nfo):
            self.assertEquals(72, nfo['length'])
        return dd.addCallback(_getLeavesForTTH)
        
    def test_sameFileTwoPlaces(self):
        self._makeFile('foo/foo.txt', size=((2**20)*2+50))
        self._makeFile('foo/bar.txt', size=((2**20)*2+50))
        dd = self.shareStore.add(FilePath('foo/foo.txt'))
        def _addBarTxt(res):
            dd = self.shareStore.add(FilePath('foo/bar.txt'))
            return dd.addCallback(_getLeavesForTTH)
        def _getLeavesForTTH(res):
            dd = self.shareStore.getLeavesForTTH(u'3RDFCYVE6YU4JJQU6UXKNXSKZDG3A7KHC6L6PMA')
            return dd.addCallback(_getByTTH)
        def _getByTTH(res):
            dd = self.shareStore.getByTTH(u'3RDFCYVE6YU4JJQU6UXKNXSKZDG3A7KHC6L6PMA')
            return dd.addCallback(_checkResults)
        def _checkResults(nfo):
            assert nfo
            
        return dd.addCallback(_addBarTxt)

    def test_getFilesXmlBz2(self):
        self._makeFile('foo/foo.txt')
        self._makeFile('foo/bar.txt', char='b')
        self._makeFile('foo/baz/qux.txt', char='c')
        dd = self.shareStore.startIndexer()
        def _getFilesXmlBz2(res):
            dd = self.shareStore.getFilesXmlBz2()
            return dd.addCallback(_checkResults)
        def _checkResults(nfo):
            self.assertEqual(True, os.path.exists('files.xml.bz2'))
            self.assertEqual(1, len(list(filelist.files('files.xml.bz2', 'Foo\\baz'))))
            self.assertEqual(3, len(list(filelist.files('files.xml.bz2', 'Foo'))))
            os.unlink('files.xml.bz2')
            
        return dd.addCallback(_getFilesXmlBz2)

    def test_indexWhenDownloadIsComplete(self):
        self._makeFile('foo/foo.txt')
        class FakeDownload:
            type = 'file'
            outfilepath = 'foo/foo.txt'
            
        res = louie.send('download:finished', self, FakeDownload())
        self.assertEqual(1, len(res))
        
        dd = res[0][1]
        def _getByTTH(res):
            dd = self.shareStore.getByTTH(u'LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI')
            return dd.addCallback(_checkResults)
        def _checkResults(nfo):
            self.assertEqual(u'Foo\\foo.txt', nfo['dcPath'])
        return dd.addCallback(_getByTTH)

    def test_haveFileWithTTH(self):
        self._makeFile('foo/foo.txt', size=((2**20)*2+50))
        dd = self.shareStore.add(FilePath('foo/foo.txt'))
        def _haveFileWithTTH(res):
            dd = self.shareStore.haveFileWithTTH(u'3RDFCYVE6YU4JJQU6UXKNXSKZDG3A7KHC6L6PMA')
            return dd.addCallback(_checkResults)
        def _checkResults(haveIt):
            self.assertEquals(FilePath, haveIt.__class__)
        return dd.addCallback(_haveFileWithTTH)

    def test_searchTTH(self):
        self._makeFile('foo/foo.txt')
        dd = self.shareStore.add(FilePath('foo/foo.txt'))
        def _doSearch(path):
            dd = self.shareStore.search('TTH:LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI', filetype=9)
            return dd.addCallback(_checkSearch)
        def _checkSearch(res):
            self.assertEquals(1, len(res))
            self.assertEquals((u'Foo\\foo.txt', 10240, u'LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI'), res[0])
        return dd.addCallback(_doSearch)

    def test_searchWithMaxSize(self):
        from twisted.internet import base
        base.DelayedCall.debug = True
        
        self._makeFile('foo/baz1.txt', size=1024)
        self._makeFile('foo/baz2.txt', size=2048)
        dd = self.shareStore.startIndexer()
        def _doSearch(path):
            dd = self.shareStore.search('baz', maxsize=1024)
            return dd.addCallback(_checkSearch)
            
        def _checkSearch(res):
            self.assertEquals(1, len(res))
            self.assertEquals((u'Foo\\baz1.txt', 1024, u'BR4BVJBMHDFVCFI4WBPSL63W5TWXWVBSC574BLI'), res[0])
            
            dd = self.shareStore.search('baz', minsize=1025)
            return dd.addCallback(_checkMinSearch)
        def _checkMinSearch(res):
            self.assertEquals(1, len(res))
            self.assertEquals((u'Foo\\baz2.txt', 2048, u'YPAYMUL6MIZR2X34IKJON6TN2KPYPNE7IHGP2MQ'), res[0])
          
        return dd.addCallback(_doSearch)
    
    def _tests_other(self):
        # that deleting a dir tree in the share doesn't leave orphaned Path rows
        # that changing the timestamp/contents of the file gets reindexed
        #leave size should be 1mb, not leave row if > 1mb
        # reactor removeSystemEventTrigger
        # what error to other dc clients give when they dont' have an answer fro a tthl
        pass

class MultiShareStoreTest(TestCase):
    @defer.inlineCallbacks
    def setUp(self):
        dbthread.setup()
        os.mkdir('foo')
        os.mkdir('bar')
        locator = components.Componentized()
        config = StubConfig(files=dict(shared=dict({'Foo': 'foo', 'Bar': 'bar'})))
        config.dataDir = FilePath(os.getcwd())
        locator.setComponent(interfaces.IConfig, config)
        self.extutilsService = extutils.ExtUtilsService()
        self.extutilsService.startService()
        locator.setComponent(interfaces.IHasher, self.extutilsService)
        locator.setComponent(interfaces.IDirLister, self.extutilsService)
        self.shareStore = sharestore.ShareStore(locator)
        self.shareStore.setupDone.addErrback(log.err)
        self.shareStore.startService()
        yield self.shareStore.setupDone

    @defer.inlineCallbacks
    def tearDown(self):
        yield self.shareStore.stopService()
        yield self.extutilsService.stopService()
        yield dbthread.thread.shutdown()
        shutil.rmtree('foo')
        shutil.rmtree('bar')
        for fn in glob.glob('*.sqlite3'):
            os.unlink(fn)
            
    def _makeFile(self, path, size=10240, char='a'):
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        ff = open(path, 'w')
        ff.write(char*size)
        ff.close()
    
    @defer.inlineCallbacks
    def testIndexing(self):
        self._makeFile('foo/foo.txt')
        self._makeFile('bar/monkey.txt')
        yield self.shareStore.startIndexer()
        res = yield self.shareStore.search('foo.txt', filter=['Bar'])
        self.assertEqual(0, len(res))
        res = yield self.shareStore.search('monkey.txt', filter=['Bar'])
        self.assertEqual(1, len(res))

    @defer.inlineCallbacks
    def test_searchTTH(self):
        self._makeFile('foo/foo.txt')
        yield self.shareStore.add(FilePath('foo/foo.txt'))
        res = yield self.shareStore.search('TTH:LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI', filetype=9, filter=['Bar'])
        self.assertEquals(0, len(res))
        res = yield self.shareStore.search('TTH:LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI', filetype=9)
        self.assertEquals(1, len(res))
        self.assertEquals((u'Foo\\foo.txt', 10240, u'LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI'), res[0])


    @defer.inlineCallbacks
    def test_getFileList(self):
        self._makeFile('foo/foo.txt')
        self._makeFile('foo/bar.txt', char='b')
        self._makeFile('bar/baz/qux.txt', char='c')
        yield self.shareStore.startIndexer()
        yield self.shareStore.getFilesXmlBz2(filter=['Bar', 'Share3'])
        self.assertEqual(True, os.path.exists('files.Bar+Share3.xml.bz2'))
        self.assertEqual(1, len(list(filelist.files('files.Bar+Share3.xml.bz2', 'Bar\\baz'))))
        self.assertRaises(filelist.NotFoundError, list, filelist.files('files.Bar+Share3.xml.bz2', 'Foo'))
        os.unlink('files.Bar+Share3.xml.bz2')


