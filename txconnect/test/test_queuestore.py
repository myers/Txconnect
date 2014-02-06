# -*- coding: utf8 -*-
import os, shutil, ntpath, time, glob

from twisted.trial.unittest import TestCase
from twisted.python import log, components
from twisted.python.filepath import FilePath
from twisted.internet import defer
import louie

from ..directconnect import interfaces, download

from .. import queuestore, dbthread
from ..queuestore import models

class StubConfig(dict):
    pass
    
class QueueStoreTest(TestCase):
    def setUp(self):
        dbthread.setup()
        locator = components.Componentized()
        config = StubConfig(files=dict(finished='/tmp'))
        locator.setComponent(interfaces.IConfig, config)
        self.queueStore = queuestore.QueueStore(locator)

    @defer.inlineCallbacks
    def tearDown(self):
        yield dbthread.thread.shutdown()
        #for fn in glob.glob('*.sqlite3'):
        #    os.unlink(fn)
            
    @defer.inlineCallbacks
    def testAddingADownloadWithoutALabel(self):
        count = yield dbthread.runReadQuery(models.File.objects.count)
        self.assertEqual(0, count)
        yield self.queueStore.download('outpath.txt', sources={'peer$hub': 'foo\\bar'})
        count = yield dbthread.runReadQuery(models.File.objects.count)
        self.assertEqual(1, count)

    @defer.inlineCallbacks
    def testAddingADownloadWithALabel(self):
        count = yield dbthread.runReadQuery(models.File.objects.count)
        self.assertEqual(0, count)
        count = yield dbthread.runReadQuery(models.Label.objects.count)
        self.assertEqual(0, count)
        yield self.queueStore.download('outpath.txt', sources={'peer$hub': 'foo\\bar'}, label='foo')
        count = yield dbthread.runReadQuery(models.File.objects.count)
        self.assertEqual(1, count)
        count = yield dbthread.runReadQuery(models.Label.objects.count)
        self.assertEqual(1, count, 'missing label row')
        count = yield dbthread.runReadQuery(models.File.objects.with_label('foo').count)
        self.assertEqual(1, count)
        