import os, time, tempfile, shutil, pprint, datetime

from twisted.python import log
from twisted.internet import reactor, error, threads, defer

import louie

from .directconnect import filelist, errors
from . import service_util
from .tth import TTH

# FIXME: Download outfilepath should be a FilePath

# TODO: progress tracking

"""
download a file, looking for and using multiple sources

1) interate over known sources, trying to get a connection to them if we can, 
2) if there is a tth for the file, search for more sources
"""

# FIXME: refactor into a SingleSourceDownloader, DirectoryDownloader, and MultiSourceDownloader

class Downloader(service_util.ServiceUtil):
    def __init__(self, locator, download):
        self.locator = locator
        self.download = download
        
        self.name = 'Downloader %x for Download %r' % (id(self), self.download.id,)
        self.log('init for %r' % (self.download.outfilepath,))
        
        self.startedAt = None
        
        self.searchStatus = None
        self.searchStartedAt = None
        self.searchDeferred = None

        self.complete = False
        
        # k: peer, v: connection to peer
        self.peers = {}
        
        self.neededBlocks = []
        self.blockSize = None
        
        # k: peer, v: list of blocks
        self.downloadingBlocks = {}
        
        self.peerRemoveReasons = {}
        self.peerProgress = {}

        self.status = 'idle'
        
        self.outFile = None
        self.tthVerifier = None
        
        self.retryCount = 0

        self.bytesTransfered = 0
        
        self.moved = False
        
        if self.download.canMultisource():
            self.incomingFilepath = os.path.join(self.config['files']['incoming'], "%s.txconnect" % (self.download.tth,))
            if self.download.leaves:
                self.neededBlocks = self.blocksNeeded()
        
        louie.connect(self.onPeerQuit, 'peer:quit')
        louie.connect(self.onPeerTimeout, 'peer:timeout')
        louie.connect(self.onPeerMaxedOut, 'peer:maxed_out')
        louie.connect(self.onHubUserQuit, 'hub:user:quit')
        louie.connect(self.onHubUserNew, 'hub:user:new')



    def cleanup(self):
        if self.searchDeferred:
            self.searchDeferred.cancel()
        self.removeAllPeers()
        louie.disconnect(self.onPeerQuit, 'peer:quit')
        louie.disconnect(self.onPeerTimeout, 'peer:timeout')
        louie.disconnect(self.onPeerMaxedOut, 'peer:maxed_out')
        louie.disconnect(self.onHubUserQuit, 'hub:user:quit')
        louie.disconnect(self.onHubUserNew, 'hub:user:new')
    
    def start(self):
        self.log("downloader started for %r" % (self.download,))
        louie.send('downloader:start', self, self.download.outfilepath, self.download.size, 0, 0)
        self.startedAt = datetime.datetime.now()
        
        try:
            dd = self.checkIfWeHaveFile()
        except Exception, ee:
            print ee
        
            
        def _afterCheck(res):
            self.log("downloader afterCheck %r" % (res,))
            if not res:
                assert self.complete, "We should be complete"
                return
            #self.outFile = self.setupIncomingFile()
            self.connectToPeers()
        dd.addCallback(_afterCheck)

    """
    returns True if we should continue
    """
    def checkIfWeHaveFile(self):
        if not self.download.canMultisource():
            return defer.succeed(True)
        if not os.path.exists(self.download.outfilepath):
            return defer.succeed(True)
        if os.path.getsize(self.download.outfilepath) != self.download.size:
            self.renameOutFile()
            return defer.succeed(True)
        
        dd = self.getHashOfFile(self.download.outfilepath)
        def _afterHash(tthroot):
            if self.download.tth != tthroot:
                self.renameOutFile()
                return True
            self.log("found file with the same name and hash, so marking download as complete")
            self.downloadFinished(0, move=False)
            return False
            
        dd.addCallback(_afterHash)
        return dd


    def getHashOfFile(self, filepath):
        dd = threads.deferToThread(TTH, filepath)
        def _afterHash(tthobj):
            return tthobj.getroot()
        dd.addCallback(_afterHash)
        return dd
        
    """
    call if you find a file in the same place we are to download to
    """
    def renameOutFile(self):
        main, ext = os.path.splitext(self.download.outfilepath)
        self.download.outfilepath = "%s.%d%s" % (main, time.time(), ext,)
        self.log("found file with same name, different size, renaming to %r" % (self.download.outfilepath,))
        self.queue.update(self.download)
    
    def cancel(self):
        self.giveUp('canceled')

    def giveUp(self, reason):
        #self.log('giveUp: %s' % (reason,))
        self.status = 'finished'
        # important that the peers are released after others know this is a failed download
        louie.send('downloader:finished', self, self.download, reason=reason)
        self.cleanup()

    def addPeer(self, peer):
        assert self.status != 'finished'
        if peer in self.peers:
            return
        if peer not in self.peerHerder.filterAndSort(self.peers.keys() + [peer]):
            return
        self.peers[peer] = None
        self.peerHerder.takeAPeer(peer, self.gotConnection)
    
    def removeAllPeers(self):
        for peer in self.peers.keys():
            self.removePeer(peer)
    
    def lookedForMorePeers(self):
        if not self.download.canMultisource():
            # I cannot look for more peers
            return True
        if self.searchStatus == 'searched':
            return True
        return False

    def deallocateBlocksFromPeer(self, peer):
        blocks = self.downloadingBlocks.pop(peer, [])
        if not blocks:
            return
        self.log('deallocating %r blocks from %r' % (len(blocks), peer,))
        self.neededBlocks.extend(blocks)
        self.neededBlocks.sort(lambda aa, bb: cmp(aa[0], bb[0]))
               
    # remove peer from active peers (not from the download itself)
    def removePeer(self, peer, reason=None):
        try:
            self.peerHerder.releaseAPeer(peer, self.gotConnection)
        except Exception, ee:
            print ee
        self.deallocateBlocksFromPeer(peer)
        connection = self.peers.pop(peer)
        if connection:
            louie.disconnect(self.onPeerDownloadStart, 'peer:download:start', connection)
            louie.disconnect(self.onPeerDownloadProgress, 'peer:download:progress', connection)
            louie.disconnect(self.onPeerDownloadEnd, 'peer:download:end', connection)
        
        if reason:
            self.log('removing peer %r because %r' % (peer, reason,))
            self.peerRemoveReasons[peer] = reason
        if self.status != 'finished' and self.lookedForMorePeers() and not self.peers:
            self.giveUp('no peers')
    
    def setStatus(self, status):
        assert getattr(self, '_status', None) != 'finished', 'trying to unset finished in %x' % (id(self),)
        self._status = status
        louie.send('downloader:status', self, self._status)
    def getStatus(self):
        return self._status
    status = property(getStatus, setStatus)

    @property
    def id(self):
        return "%x" % (id(self),)
             
    def __repr__(self):
        return "<%s for %r %x>" % (self.__class__, self.download, id(self),)

    def __del__(self):
        if self.download.canMultisource() and self.complete:
            assert not os.path.exists(self.incomingFilepath), "still here: %r" % (self.incomingFilepath,)
        #self.log('good bye cruel world')
        
    def whereInLineForPeers(self):
        ret = []
        for peer in self.peers.keys():
            ret.append((peer, self.peerHerder.whereInLineForPeer(peer, self.gotConnection),))
        ret.sort(lambda aa, bb: cmp(aa[1], bb[1]))
        return ret
        
    def searchForSources(self):
        if self.searchStatus:
            self.log('I was asked to search again')
            import traceback
            traceback.print_stack()
            return
        #self.log('searchForSources')
        self.status = 'searching'
        self.searchStatus = 'searching'

        def _useSearchResults(results):
            self.searchDeferred = None
            if self.status == 'finished':
                return
            for res in results:
                if res['peer'] not in self.download.peerPathnames:
                    self.download.peerPathnames[res['peer']] = res['filepath']
                self.addPeer(res['peer'])
            #self.log('update')
            self.queue.update(self.download)
            self.status = 'ready'
            self.searchStatus = 'searched'

            if not self.peers:
                self.giveUp('no peers')
                return
            #self.log('we now have these peers: %r' % (self.peers.keys(),))
            
            if abs(min([place for peer, place in self.whereInLineForPeers()])) > 0:
                self.giveUp('all peers waiting on other downloads')
                return                
        try:
            self.searchDeferred = self.searchHerder.searchWithResults('TTH:%s' % (self.download.tth,), filetype=9)
            self.searchStartedAt = datetime.datetime.now()
            self.searchDeferred.addCallbacks(_useSearchResults, log.err)
        except Exception, ee:
            print "some error while searching %r, fix this so it is more specific" % (ee,)
            import traceback
            traceback.print_exc()
            self.searchStatus = None
            reactor.callLater(60, self.searchForSources)

    def connectToPeers(self):
        self.status = 'connecting'
        #self.log('connectToPeers')
        if self.download.canMultisource() and not self.searchStatus:
            self.searchForSources()
        peers = self.peerHerder.filterAndSort(self.download.peerPathnames.keys())
        if not peers:
            if not self.download.canMultisource():
                self.giveUp('no peers, cannot multisource')
            elif self.searchStatus == 'searched':
                self.giveUp('no peers')
            return
        for peer in peers:
            self.addPeer(peer)
        
    def gotConnection(self, connection):
        assert connection
        assert connection.status == "idle", "%r" % (connection,)
        assert connection.peer in self.peers
        assert self.status != 'finished'
        
        louie.connect(self.onPeerDownloadStart, 'peer:download:start', connection)
        louie.connect(self.onPeerDownloadProgress, 'peer:download:progress', connection)
        louie.connect(self.onPeerDownloadEnd, 'peer:download:end', connection)
        
        self.peers[connection.peer] = connection
        #self.log('about to start download from %s' % (connection.peer,))
        if self.download.type == 'directory':
            self.getDirectory(connection)
        elif self.download.type == 'filelist':
            self.getFileList(connection)
        elif self.download.canMultisource() and connection.supportsBlocks():
            self.getBlocks(connection)
        elif self.download.canMultisource() and not connection.supportsBlocks() and len(self.peers) > 1:
            self.log('a peer %r cannot multisource' % (connection.peer,))
            self.removePeer(connection.peer, 'cannot multisource')
        else:
            self.getFile(connection)
            
    def getFile(self, connection):
        self.outFile = self.setupIncomingFile()
        dd = connection.getFile(
          self.outFile, 
          self.download.peerPathnames[connection.peer], 
          length=self.download.size, 
          offset=self.download.offset, 
          tth=self.download.tth,
          priority=self.download.priority,
        )
        dd.addCallbacks(
            callback=self.downloadFinished,
            callbackArgs=(connection,),
            errback=self.handleError, 
            errbackArgs=(connection.peer,))
        dd.addErrback(self.handleFileNotAvailableError, connection)

    def getFileList(self, connection):
        self.outFile = self.setupIncomingFile()
        dd = connection.getFileList(
          self.outFile, 
          priority=self.download.priority,
        )
        dd.addCallbacks(
            callback=self.downloadFinished,
            callbackArgs=(connection,),
            errback=self.handleError, 
            errbackArgs=(connection.peer,))
        dd.addErrback(self.handleFileNotAvailableError, connection)


    # TODO: refactor with fire... oh my goodness. also verification should happen on a per block level,
    # not just at the end of the download
    def getBlocks(self, connection):
        dd = connection.getLeaves(self.download.tth, self.download.priority)
        def _onLeavesDownloaded(leaves):
            if self.download.leaves:
                if leaves != self.download.leaves:
                    if len(leaves) != len(self.download.leaves):
                        self.log('got different size leaves %r vs %r' % (len(leaves), len(self.download.leaves),))
                    else:
                        self.log('got different leaves!!! %r vs %r' % (len(leaves), len(self.download.leaves),))
                else:
                    self.log('leaves are the same')
            else:
                self.download.leaves = leaves
                self.queue.update(self.download)
                self.neededBlocks = self.blocksNeeded()
            return _downloadSomeBlocks()
        def _downloadSomeBlocks(res=None, blocks=None):
            assert self.status != 'finished'
            if blocks:
                assert self.downloadingBlocks[connection.peer] == blocks, 'blocks I downloaded aren\'t the same as was assigned'
                self.downloadingBlocks.pop(connection.peer)

            if len(self.neededBlocks) == 0 and len(self.downloadingBlocks) > 0:
                self.removePeer(connection.peer, 'no more blocks for %r to download' % (connection.peer,))
                return
            if len(self.neededBlocks) == 0 and len(self.downloadingBlocks) == 0:
                self.neededBlocks = self.blocksNeeded()
                if len(self.neededBlocks) == 0:
                    self.log('download finished by peer %r' % (connection.peer,)) 
                    self.downloadFinished(res, connection)
                    return
                else:
                    self.log('corrupt blocks found, redownloading')
            myBlocks = []
            myBlocks.append(self.neededBlocks.pop(0))
            offset, byteCount = myBlocks[0]
            while byteCount < 1 * 1048576 and self.neededBlocks:
                block = self.neededBlocks[0]
                if offset + byteCount != block[0]:
                    self.log('non contiguious block %r %r %r' % (offset, byteCount, block,))
                    break
                myBlocks.append(self.neededBlocks.pop(0))
                byteCount += block[1]
            
            self.log('allocating %r blocks to %r' % (len(myBlocks), connection.peer,))
            self.downloadingBlocks[connection.peer] = myBlocks[:]
            #self.log('peer %r %r' % (connection.peer, myBlocks[0],))
            dd = connection.getFile(
              self.setupIncomingFile, 
              self.download.peerPathnames[connection.peer], 
              offset=offset, 
              length=byteCount, 
              tth=self.download.tth,
              priority=self.download.priority,
            )
            dd.addCallbacks(
                callback=_downloadSomeBlocks,
                callbackArgs=(myBlocks,),
                errback=self.handleError, 
                errbackArgs=(connection.peer,))
            dd.addErrback(self.handleFileNotAvailableError, connection)
            return dd

        dd.addCallbacks(
            callback=_onLeavesDownloaded,
            errback=self.handleError, 
            errbackArgs=(connection.peer,))
        dd.addErrback(self.handleFileNotAvailableError, connection)
        return dd
        
    def handleFileNotAvailableError(self, res, connection):
        res.trap(errors.FileNotAvailableError)
        if self.download.type == 'filelist':
            self.giveUp('Peer told us he does not have a file list.')
            return
            
        if not self.download.stupidPeerMode and len(self.peers) == 1:# and self.searchStatus == 'searched':
            self.log('Failed to get tthl, but this is the only peer %r and he responded to our search. Switching to stupid mode' % (connection.peer,))
            self.download.stupidPeerMode = True
            self.getFile(connection)
            return
        
        self.log("FileNotAvailableError: Removing peer %r from download %r from queue" % (connection.peer, self.download,))
        self.download.peerPathnames.pop(connection.peer, None)
        dd = self.queue.update(self.download)
        def _afterRemove(res):
            self.removePeer(connection.peer, 'File not available')
        def _writeErrorLog(failure):
            failure.trap(Exception)
            open('errorlog.txt', 'w').write("%r %r" % (failure, failure.getTraceback(),))
        dd.addCallbacks(_afterRemove, log.err)
    
    def isConnecting(self):
        if self.status == 'finished':
            return False
        return set(self.peers.values()) == set((None,))
    
    def handleError(self, res, peer):
        err = res.trap(errors.MaxedOutError, error.ConnectionLost, errors.PeerNoLongerConnectedError)
        if err == errors.PeerNoLongerConnectedError:
            self.removePeer(peer, 'no longer connected')
            return

    def downloadFinished(self, res, connection=None, move=True):
        self.log("finished")
        assert self.status != 'finished'
        #self.log('downloadFinished: %r' % (self.download.outfilepath,))
        self.status = 'finished'
        self.complete = True
        if move:
            self.moveFileToDestinaton()
        #self.queue.remove(self.download)
        louie.send('downloader:finished', self, self.download, reason='complete', result=res)
        louie.send('download:finished', self, self.download, result=res)
        self.cleanup()

    def moveFileToDestinaton(self):
        #self.log('moveFileToDestinaton')
        
        assert not self.moved
        
        # move contents from temp file to new file
        if not os.path.exists(os.path.dirname(self.download.outfilepath)):
            os.makedirs(os.path.dirname(self.download.outfilepath))
        if not self.download.canMultisource():
            outFile = self.outFile
            outFile.seek(0)
        else:
            outFile = self.setupIncomingFile()
        assert not isinstance(self.download.outfilepath, unicode), "%r is unicode" % (self.download.outfilepath,)
        out = file(self.download.outfilepath, 'wb')
        shutil.copyfileobj(outFile, out)
        out.close()
        outFile.close()
        
        if self.download.canMultisource():
            assert outFile.name == self.incomingFilepath, '%r vs %r' % (outFile.name, self.incomingFilepath,)
        if os.path.exists(outFile.name):
            os.unlink(outFile.name)
        
        self.moved = True

    def getDirectory(self, connection):
        filelistDir = self.config.dataDir.child('filelists')
        if not self.config.dataDir.child('filelists').exists():
            self.config.dataDir.child('filelists').makedirs()
        
        filelistpath = filelistDir.child(connection.peer.nick.encode('utf-8') + '.xml.bz2')
        if filelistpath.exists() and (time.time() - filelistpath.getmtime()) < 10 * 60:
            dd = self.queueFilesInDirectory(
              connection.peer, 
              filelistpath.path, 
              self.download.peerPathnames[connection.peer], 
              self.download.outfilepath
            )
            dd.addCallback(self._afterFilesQueued)
        else:
            ff = filelistpath.open('w+b')
            dd = connection.getFileList(ff)
            dd.addCallback(self.fileListDownloadFinished, ff, connection)

    def fileListDownloadFinished(self, result, fileobj, connection):
        fileobj.close()
        dd = self.queueFilesInDirectory(connection.peer, fileobj.name, self.download.peerPathnames[connection.peer], self.download.outfilepath)
        dd.addCallback(self._afterFilesQueued)

    def _afterFilesQueued(self, res):
        if res:
            louie.send('downloader:finished', self, self.download, reason='complete')
        else:
            louie.send('downloader:finished', self, self.download, reason='error reading filelist')
        self.status = 'finished'
        self.complete = True
        self.cleanup()

    def queueFilesInDirectory(self, peer, filelistpath, peerpath, outfilepath):
        def _queueFilesInDirectory():
            try:
                for fullDcPath, relativeUnixPath, size, tth in filelist.files(filelistpath, peerpath):
                    sources = {peer: fullDcPath}
                    reactor.callFromThread(self.queue.download, os.path.join(outfilepath, relativeUnixPath), tth=tth, size=size, sources=sources, priority=self.download.priority)
            except EOFError:
                log.err('incomplete filelist, deleting: %r' % (filelistpath,))
                os.unlink(filelistpath)
                return False
            return True
        return threads.deferToThread(_queueFilesInDirectory)

    def setupIncomingFile(self):
        if not os.path.isdir(self.config['files']['incoming']):
            os.makedirs(self.config['files']['incoming'])
        if self.download.outFile is None:
            assert self.download.outfilepath, pprint.pformat(self.download.__dict__)
            if self.download.canMultisource():
                mode = 'w+b'
                if os.path.isfile(self.incomingFilepath):
                    mode = 'r+b'
                outFile = open(self.incomingFilepath, mode)
                outFile.truncate(self.download.size)
                return outFile
            else:
                suffix = "-" + os.path.basename(self.download.outfilepath)
                outFile = tempfile.NamedTemporaryFile(dir=self.config['files']['incoming'], suffix=suffix)
        return outFile

    # FIXME: this should be run in another thread
    def blocksNeeded(self):
        assert self.download.leaves
        try:
            if self.tthVerifier is None:
                self.tthVerifier = TTH(fileName=self.incomingFilepath, root=self.download.tth, leaves=self.download.leaves, fileSize=self.download.size)
        except ValueError:
            log.msg('%r: bad leave data tth: %r, leaves: %r' % (self, self.download.tth, self.download.leaves,))
            raise
            
        ret = self.tthVerifier.blocksNeeded()
        log.msg('We need %d blocks of %d' % (len(ret), self.tthVerifier.blockCount(),))
        return ret

    def allDownloadingBlocks(self):
        ret = []
        for blocks in self.downloadingBlocks.values():
            ret.extend(blocks)
        return ret
        
    def peerStatus(self):
        ret = {}
        for peer, place in self.whereInLineForPeers():
            if place > 0:
                info = dict(status='waiting on other download')
            elif place < 0:
                info = dict(status='not registered (downloader has it but peer herder doesn\'t)')
            elif self.peers[peer]:
                info = dict(status='connected')
            else:
                info = dict(status='waiting', more=self.peerHerder.peerStatus.get(peer, None))
            info['blockCount'] = len(self.downloadingBlocks.get(peer, []))
            info['connection'] = self.peers[peer]
            ret[peer] = info
        for peer in self.download.peerPathnames.keys():
            if peer in ret:
                continue
            if peer in self.peerHerder.allPeers:
                if peer in self.peerRemoveReasons:
                    ret[peer] = dict(status='removed for: %s' % (self.peerRemoveReasons[peer],))
                else:
                    ret[peer] = dict(status='not registered (the download has it listed as a peer)')
            else:
                ret[peer] = dict(status='offline')
        return ret

    def onPeerMaxedOut(self, peer, data):
        if peer not in self.peers:
            return
        if not self.searchStatus and self.download.canMultisource():
            self.searchForSources()
            return
   
    def onPeerTimeout(self, peer):
        if not self.peers.has_key(peer):
            return
        if not self.searchStatus and self.download.canMultisource():
            self.log('fuck this guy %r, he timed out on us... is there anyone else with this file?' % (peer,))
            self.removePeer(peer, 'jerk')
            self.searchForSources()
            return
        self.retryCount += 1
        if self.retryCount > 5 and len(self.peers) == 1:
            self.giveUp('only peer is timed out')
    
    def onPeerQuit(self, connectionId, status, sender=None):
        peer = sender.peer
        if peer not in self.peers:
            return
        self.peers[peer] = None
        self.deallocateBlocksFromPeer(peer)
        if self.isConnecting():
            self.status = 'connecting'
       
    def onHubUserNew(self, hubId, peer):
        #assert peer not in self.peers
        if peer not in self.download.peerPathnames:
            return
        if peer not in self.peers:
            self.addPeer(peer)
    
    def onHubUserQuit(self, hubId, peer):
        if peer not in self.peers:
            return
        # don't remove the peer if we have a working connection with him
        if self.peers[peer] is None:
            self.removePeer(peer, 'quit hub')
    
    def onPeerDownloadStart(self, connectiondId, path, bytesToTransfer, bytesTransfered, rate, sender=None):
        if self.status != 'finished':
            self.status = 'downloading'
        self.peerProgress[sender.peer] = (bytesToTransfer, bytesTransfered,)
    
    def onPeerDownloadProgress(self, connectionId, bytesToTransfer, bytesTransfered, rate, sender=None):
        peer = sender.peer
        if not self.download.canMultisource():
            louie.send('downloader:progress', self, bytesToTransfer, bytesTransfered, rate)
            return
        
        self.peerProgress[peer] = (bytesToTransfer, bytesTransfered,)

        if not self.tthVerifier:
            # TODO: rate
            louie.send('downloader:progress', self, self.download.size, self.bytesTransfered, 0)
            return
        
        #| downloaded | peers | unclamied self.neededBlocks |
        blockSize = self.tthVerifier.blockSize()
        
        old = self.bytesTransfered
        
        
        """
     _              
 ___| |_ ___  _ __  
/ __| __/ _ \| '_ \ 
\__ \ || (_) | |_) |
|___/\__\___/| .__/ 
             |_|    

make a unit test
"""        
        bytesNeeded = sum([aa[1] for aa in self.neededBlocks])
        bytesForPeers = sum([aa[1] for aa in self.allDownloadingBlocks()])
        bytesForPeers2 = sum([pp[0] for pp in self.peerProgress.values()])
        
        #if bytesForPeers != bytesForPeers2:
        #    warnings.warn('maybe this is the problem %r %r' % (bytesForPeers, bytesForPeers2,))
        
        self.bytesTransfered = self.download.size - bytesNeeded - bytesForPeers
        self.bytesTransfered += sum([pp[1] for pp in self.peerProgress.values()])
        #if old > self.bytesTransfered:
        #    warnings.warn('humm, we went backwards in bytesTransfered old %r new %r' % (old, self.bytesTransfered,))
        
        # TODO: rate
        louie.send('downloader:progress', self, self.download.size, self.bytesTransfered, 0)

    def onPeerDownloadEnd(self, connectiondId, bytesToTransfer, bytesTransfered, rate, sender=None):
        self.peerProgress.pop(sender.peer, None)
        
    @property
    def active(self):
        activePeers = [peer for peer, connection in self.peers.items() if connection]
        return len(activePeers) > 0 or not self.lookedForMorePeers()
