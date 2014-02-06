from twisted.trial.unittest import TestCase
from twisted.python import components
from twisted.internet import defer
from twisted.test import proto_helpers

from .. import downloader_manager
from ..directconnect import peer, interfaces

import louie

from flexmock import flexmock

class DownloaderManagerTest(TestCase):
    def setUp(self):
        self.peer1 = peer.Peer('foo$bar.com')
        self.locator = components.Componentized()

        self.downloadQueue = flexmock()
        self.locator.setComponent(interfaces.IDownloadQueue, self.downloadQueue)
        self.downloadQueue.should_receive("cleanIncomingFiles").with_args().once()

        self.downloaderManager = downloader_manager.DownloaderManager(self.locator)
        self.downloaderManager.startService()

        self.download = flexmock(id=1, priority=100, canMultisource=lambda: True)

    def tearDown(self):
        return self.downloaderManager.stopService()
        
    def testNewPeerStartsDownloader(self):
        self.downloadQueue.should_receive('getNextForPeer').with_args(self.peer1).and_return(defer.succeed(self.download))
        #self.downloader.should_receive('start').once()

        louie.send('hub:user:new', self, None, self.peer1, me=False)

    def testEnqueuingDownloadStartsDownloader(self):
        self.downloader = flexmock()
        self.downloader.should_receive('start').once()
        self.downloader.should_receive('cancel').once()
        
        flexmock(StubDownloaderFactory).new_instances(self.downloader).once()
        self.downloaderManager.downloaderFactory = StubDownloaderFactory

        louie.send('download:queued', self, self.download)

class StubDownloaderFactory(object):
    def __init__(self, locator, download):
        pass
