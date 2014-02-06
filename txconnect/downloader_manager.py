import datetime, traceback

from twisted.python import log
from twisted.internet import reactor, defer, task
from twisted.application import service

from zope.interface import implements
import louie

from .directconnect import interfaces
from . import service_util, downloader


def withDeferredLock(lockName):
    def _withDeferredLock(func):
        def _wrapped(self, *args, **kwargs):
            if not hasattr(self, lockName):
                setattr(self, lockName, defer.DeferredLock())
            lock = getattr(self, lockName)
            dd = lock.acquire()
            def _call(lock):
                return func(self, *args, **kwargs)
            dd.addCallbacks(_call, log.err)
            def _release(res):
                lock.release()
            dd.addBoth(_release)
            return dd
        return _wrapped
    return _withDeferredLock


class DownloaderManager(service.Service, service_util.ServiceUtil):
    implements(interfaces.IDownloaderManager)

    name = 'downloaderManager'    

    downloaderFactory = downloader.Downloader
    timeout = 60
    maxDownloaders = 15

    def __init__(self, locator):
        self.locator = locator
        
        self.downloaders = {}
        
        # k: download id, v: datetime last tried
        self.failingDownloads = {}
        
        self.addMoreDownloaderCall = task.LoopingCall(self.addMoreDownloader)
        self.startedAt = None
        self.settledHubs = []

    def startService(self):
        service.Service.startService(self)
        louie.connect(self.onHubUserNew, 'hub:user:new')
        louie.connect(self.onDownloadQueued, 'download:queued')
        louie.connect(self.onDownloaderFinished, 'downloader:finished')

        louie.connect(self.onDownloaderStatus, 'downloader:status')
        louie.connect(self.onPeerIdle, 'peer:idle')
        louie.connect(self.onHubConnected, 'hub:connected')
        louie.connect(self.onHubQuit, 'hub:quit')
        self.addMoreDownloaderCall.start(30, now=False)
        self.queue.cleanIncomingFiles()
        
        self.startedAt = datetime.datetime.now()
    
    def stopService(self):
        service.Service.stopService(self)
        louie.disconnect(self.onHubUserNew, 'hub:user:new')
        louie.disconnect(self.onDownloadQueued, 'download:queued')
        louie.disconnect(self.onDownloaderFinished, 'downloader:finished')
        louie.disconnect(self.onDownloaderStatus, 'downloader:status')
        louie.disconnect(self.onPeerIdle, 'peer:idle')
        louie.disconnect(self.onHubConnected, 'hub:connected')
        louie.disconnect(self.onHubQuit, 'hub:quit')
        self.log('stopping addMoreDownloaderCall')
        for dl in self.downloaders.values():
            try:
                dl.cancel()
            except Exception, ee:
                log.err(ee)
        
        self.addMoreDownloaderCall.stop()
        

    def onPeerIdle(self, peer):
        self.log('finding download for idle peer %r' % (peer,))
        self.nextDownloadForPeer(peer, force=True)
    
    def onDownloaderStatus(self, status, caller=None):
        pass
        
    def onDownloadQueued(self, download):
        self.log('onDownloadQueued')
        # HACK: we need a way to know if we are limiting downloads of a certian priority
        if download.priority < 10:
            return
        elif download.priority < 50:
            force = False
        else:
            force = True
        self.startDownloader(download, force=force)

    def onDownloaderFinished(self, download, reason=None, result=None):
        self.log('onDownloaderFinished: %r, reason: %r, result: %r' % (download.id, reason, result,))
        if reason != 'complete':
            self.addToFailingDownloads(download.id)
        if reason == 'complete':
            #print "about to call remove download for %r" % (download.id,)
            dd = self.removeDownload(download)
            dd.addCallback(lambda res: self.log('removed download from queue: %r' % (download,)))
            dd.addErrback(log.err)
        del self.downloaders[download.id]

    @withDeferredLock('queueLock')
    def removeDownload(self, download):
        #print "Removing download id %d" % (download.id,)
        return self.queue.remove(download)
        
    def onHubUserNew(self, hubId, peer, info=None, me=False):
        if me:
            return
        if not self.wantMoreDownloaders():
            return
        self.log('finding download for new peer %r' % (peer,))
        self.nextDownloadForPeer(peer)

    def onHubConnected(self, hubId, name):
        def _afterHubHasSettledDown():
            self.settledHubs.append(hubId)
            self.addMoreDownloaderCall()
        reactor.callLater(5, _afterHubHasSettledDown)

    def onHubQuit(self, hubId, reason):
        if hubId in self.settledHubs:
            self.settledHubs.remove(hubId)
    
    def addToFailingDownloads(self, downloadId):
        assert downloadId not in self.failingDownloads, "%r %r" % (downloadId, self.failingDownloads.keys(),)
        self.log('adding %r to failingDownloads' % (downloadId,))
        self.failingDownloads[downloadId] = datetime.datetime.now()
        self.expireFailingDownloads()
    def expireFailingDownloads(self):
        for key, val in self.failingDownloads.items():
            delta = datetime.datetime.now() - val 
            if delta.seconds > 60 * 60:
                self.log('removing %r from failingDownloads' % (key,))
                del self.failingDownloads[key]
    
    @property
    def activeDownloaders(self):
        return dict([(downloadId, downloader,) for downloadId, downloader in self.downloaders.items() if downloader.active])

    def wantMoreDownloaders(self):
        if len(self.activeDownloaders) >= self.maxDownloaders:
            self.log('addMoreDownloader: too many %d' % (len(self.activeDownloaders),))
            return False
        return True

    def isGoodDownload(self, downloadId):
        return downloadId not in self.downloaders.keys() + self.failingDownloads.keys()

    @withDeferredLock('queueLock')
    def nextDownloadForPeer(self, peer, force=False):
        #print "looking for downloads for peer %r" % (peer,)
        if peer.hubId not in self.settledHubs:
            self.log('not looking for nextDownloadForPeer because we just connected to this hub')
            return

        test = None   
        if not force:
            test = self.isGoodDownload
          
        dd = self.queue.getNextForPeer(peer, test=test)
        def _afterGetNextForPeer(download):
            foo = None
            if download:
                foo = download.id
            self.log("found the next download for %r: %r" % (peer, foo,))
            if not download:
                return
            if peer in self.peerHerder.checkedOutPeers:
                self.log('not starting new downloader for %r as they are already checked out by some other download' % (peer,))
                return
            self.startDownloader(download, force)
        dd.addCallbacks(_afterGetNextForPeer, log.err)
        dd.addErrback(log.err)
        return dd

    @withDeferredLock('queueLock')
    def addMoreDownloader(self):
        # when we've stopped this service we still have stuff queued up in the DeferredLock
        # then short circuit 
        if not self.running:
            return
        
        if not self.wantMoreDownloaders():
            return
        
        if len(self.hubHerder.hubs) == 0:
            #self.log('addMoreDownloader: not connected to any hubs, try this later')
            return
        
        self.expireFailingDownloads()
        
        peers = [peer for peer in self.peerHerder.inactivePeers if peer.hubId in self.settledHubs]
        dd = self.queue.findBestDownloadOtherThanThese(self.isGoodDownload, peers)
        def _gotDownload(download):
            self.log('got download %r' % (download,))        
            if download:
                assert download.id not in self.downloaders.keys()
                assert download.id not in self.failingDownloads.keys()
                if not download.canMultisource() and not self.peerHerder.isOnline(download.peers[0]):
                    self.addToFailingDownloads(download)
                self.startDownloader(download)
                self.addMoreDownloaderCall()
        dd.addCallbacks(_gotDownload, log.err)
        dd.addErrback(log.err)
        return dd

    def startDownloader(self, download, force=False):
        #self.log("startDownloader: how did we get here? %s" % (traceback.format_stack(),))
        #self.log("startDownloader: download %r force %r" % (download, force,))
        assert download.id
        if not download.canMultisource() and download.peers[0] in self.peerHerder.checkedOutPeers:
            self.log('not starting a downloader for file with one peer that is already busy')
            return
        if download.id in self.downloaders:
            self.log('already had a downloader for this download %r' % (download,))
            return
        if not force and not self.wantMoreDownloaders():
            self.log("startDownloader: not starting downloader for %r because I don't want any more and I wasn't forced" % (download.id,))
            return
        if force and download.id in self.failingDownloads.keys():
            self.failingDownloads.pop(download.id)
        self.log("startDownloader: creating downloader %r" % (download.id,))
        dler = self.downloaderFactory(self.locator, download)
        self.downloaders[download.id] = dler
        self.downloaders[download.id].start()
        self.log("startDownloader: started downloader %r" % (dler.name,))

    def pauseDownload(self, downloadId):
        if not downloadId in self.downloaders:
            return
        self.downloaders[downloadId].cancel()

    def cancelDownload(self, downloadId):
        self.pauseDownload(downloadId)
        return self.queue.removeById(downloadId)
