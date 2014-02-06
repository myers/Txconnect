import random, time, weakref, StringIO

from twisted.python import log
from twisted.internet import protocol, defer
import twisted.internet.error
from twisted.protocols import policies, basic

import louie

from ..directconnect import DC_ENCODING

from . import utils, errors, interfaces

class PeerProtocol(basic.LineReceiver, policies.TimeoutMixin):
    delimiter = "|"
    timeOut = 300
    
    def __init__(self, connecting=True, application=None):
        self.application = application
        
        self.factory = None
        self.connecting = connecting
        self.remoteNick = None
        self.direction = "Upload"
        self.err = None
        self.remoteSupports = []
        self.setStatus('connecting')
        self.peer = None
        self.hasSlot = False
        self.lockLine = None
        
        self.commands = []
        
        self.currentTransfer = None
        
        self.expectResponse = None
        
    def __repr__(self):
        return "<%s for %r status:%r xfer:%r>" % (self.__class__, self.peer, self.status, self.currentTransfer)

    
    def setStatus(self, status):
        self.status = status
        louie.send('peer:status', self, self.status)
        
    def log(self, msg):
        log.msg(msg, system="%s" % (self.peer,))

    @property
    def fileSource(self):
        return interfaces.IFileSource(self.application)

    @property
    def config(self):
        return interfaces.IConfig(self.application)

    @property
    def peerHerder(self):
        return interfaces.IPeerHerder(self.application)

    @property
    def hubHerder(self):
        return interfaces.IHubHerder(self.application)

    def supportsBlocks(self):
        if 'ADCGet' not in self.remoteSupports:
            return False
            
        #nfo = self.peerHerder.peerInfo(self.peer)
        #if nfo['clientVersion'] == '0.698':
        
        return True

    def maybeBrokenBeyondRepair(self):    
        # this was in there for Baka 
        if 'DCPLUSPLUS0.698' in self.lockLine:
            return True
        return False

    def connectionMade(self):
        self.setTimeout(self.timeOut)
        self.setStatus('handshaking')
    
    def timeoutConnection(self):
        self.err = "timeout"
        if self.transport is not None:
            self.transport.loseConnection()
        
    def connectionLost(self, reason):
        reason.trap(twisted.internet.error.ConnectionDone, twisted.internet.error.ConnectionLost)
        if self.status == "idle":
            self.log("connection lost while idle with %r, err %r" % (self.peer, self.err,))
            louie.send('peer:quit', self, id(self), 'idle', reason=reason)
        else:
            self.log("connectionLost with %r, status: %r, reason: %r, dl: %r" % (self.peer, self.status, reason, self.currentTransfer,))
            louie.send('peer:quit', self, id(self), "%r" % (reason,), reason=reason)
        if self.currentTransfer:
            self.currentTransfer.deferred.errback(reason)
            kwargs = dict(error=True)
            louie.send('peer:%s:end' % (self.currentTransfer.type,), self, id(self), *self.currentTransfer.status(), **kwargs)
        if self.hasSlot:
            self.peerHerder.releaseASlot(self.peer)
            self.hasSlot = False

    def dataReceived(self, data):
        """Protocol.dataReceived.
        Translates bytes into lines, and calls lineReceived (or
        rawDataReceived, depending on mode.)
        """
        self._LineReceiver__buffer = self._LineReceiver__buffer+data
        while self.line_mode and not self.paused:
            try:
                if len(self._LineReceiver__buffer) > 0 and self._LineReceiver__buffer[0] == '$':
                    line, self._LineReceiver__buffer = self._LineReceiver__buffer.split('|', 1)
                else:
                    line, self._LineReceiver__buffer = self._LineReceiver__buffer.split('\n', 1)
            except ValueError:
                if len(self._LineReceiver__buffer) > self.MAX_LENGTH:
                    line, self._LineReceiver__buffer = self._LineReceiver__buffer, ''
                    return self.lineLengthExceeded(line)
                break
            else:
                linelength = len(line)
                if linelength > self.MAX_LENGTH:
                    exceeded = line + self._LineReceiver__buffer
                    self._LineReceiver__buffer = ''
                    return self.lineLengthExceeded(exceeded)
                why = self.lineReceived(line)
                if why or self.transport and self.transport.disconnecting:
                    return why
        else:
            if not self.paused:
                data=self._LineReceiver__buffer
                self._LineReceiver__buffer=''
                if data:
                    return self.rawDataReceived(data)

    def lineReceived(self, line):
        self.resetTimeout()
        self.log("<<< %r" % line)
        cmd, data = utils.parseCommand(line, client=True)
        phandler = getattr(self, "handle%s" % (cmd,), None)


        # disconnect folks that keep asking for the same thing over and over
        repeated = 0
        for ii in self.commands:
            if line == ii:
                repeated += 1
        if repeated > 5:
            self.log('Telling %r to buzz off.  He asked for %r too many times.' % (self.peer, line,))
            self.transport.loseConnection()
            return
        if line.startswith('$ADCGET'):
            self.commands.append(line)

        self.expectResponse = None
        if phandler:
            phandler(data)
        else:
            self.log("can't handle cmd: %r"% (cmd,))

    def sendLine(self, line):
        self.log(">>> %r" % line)
        basic.LineReceiver.sendLine(self, line)
    
    def sendAndWait(self, line):
        assert self.expectResponse is None, "%r expected response from this command %r" % (self, self.expectResponse,)
        self.sendLine(line)
        self.expectResponse = line
        
    def startHandshake(self):
        self.sendLine("$MyNick %s" % (self.hub.cred['nick'],))
        #                    EXTENDEDPROTOCOLABCABCABCABCABCABC Pk=DCPLUSPLUS0.674ABCABC
        #                    EXTENDEDPROTOCOLABCABCABCABCABCABC Pk=DCPLUSPLUS0.668ABCABC
        self.sendLine("$Lock EXTENDEDPROTOCOLABCABCABCABCABCABC Pk=TXCONNECT1.0ABCABCABC")

    def handleLock(self, lock):
        self.lockLine = lock
        if not self.connecting:
            self.startHandshake()

        if self.maybeBrokenBeyondRepair():
            self.sendLine("$Supports XmlBZList")
        else:
            self.sendLine("$Supports XmlBZList ADCGet TTHF TTHL")
        self.coinToss = random.randint(0, 32767)
        self.sendLine("$Direction %s %s" % (self.direction, self.coinToss,))
        self.sendLine("$Key %s" % (utils.lockToKey(lock),))
        
        if self.connecting:
            self.setStatus('idle')

    def handleSupports(self, supports):
        self.remoteSupports = supports.split()

    def handleKey(self, key):
        if not self.connecting:
            self.setStatus('idle')
        if self.direction == "Download":
            self.peerHerder.registerConnection(self)

    def handleMyNick(self, nick):
        self.remoteNick = nick.decode(DC_ENCODING)
        if not self.connecting:
            self.peer = self.factory.gotConnectionFromNick(self.remoteNick)
            self.hub = self.hubHerder.hubForPeer(self.peer)
        else:
            self.peer = self.hub.peerForNick(self.remoteNick)
        louie.send('peer:new', self, id(self), self.remoteNick, self.peer.hubId)
        if self.peerHerder.anyDownloadsNeededFromNick(self.remoteNick):
            self.direction = "Download"

    def handleDirection(self, remoteDirection):
        remoteDirection, coinToss = remoteDirection.split(None,1)
        if not (remoteDirection == "Upload" or self.coinToss > coinToss):
            self.direction = "Upload"
    
    def handleMaxedOut(self, data):        
        assert self.currentTransfer
        dl, dd = self.downloadCleanup(True)
        self.setStatus('maxedOut')
        louie.send('peer:maxed_out', self, self.peer, data)
        dd.errback(errors.MaxedOutError(data))
            
    def handleError(self, data):
        self.log('handle error: %r %r' % (data, self.currentTransfer,))
        if self.currentTransfer:
            if data == "File Not Available" or data.lower().startswith("file not found"):
                self.log('file not found error')
                if not self.currentTransfer.leaves:
                    louie.send('peer:file_not_found', self, peer=self.peer, tth=str(self.currentTransfer.tth), path=self.currentTransfer.dcPath.encode('utf-8'))
                err = errors.FileNotAvailableError(self.peer, self.currentTransfer.dcPath)
            else:
                err = errors.ParseError(data)
            
            dl, dd = self.downloadCleanup(True)
            dd.errback(err)  
    
    def getLeaves(self, tth, priority=0):
        if "ADCGet" not in self.remoteSupports:
            raise Exception('peer client does not support ADCGet')

        outfile = StringIO.StringIO()
        self.currentTransfer = Transfer(
          'download',
          dcPath='<<leaves>>',
          fileobj=outfile,
          tth=tth,
          priority=priority,
          leaves=True
        )
        self.sendAndWait("$ADCGET tthl TTH/%s %d %d" % (str(self.currentTransfer.tth), self.currentTransfer.offset, self.currentTransfer.length,))
        
        def _tthlFinished(res):
            return outfile.getvalue()
        return self.currentTransfer.deferred.addCallback(_tthlFinished)
        
    def getFile(self, outfile, filepath, offset=0, length=-1, tth=None, filelist=False, priority=0):
        self.setStatus('downloading')
        assert outfile is not None
        assert type(offset) is int
        if not length:
            length = -1
        assert (type(length) in [int, long]), length
        self.currentTransfer = Transfer(
          'download',
          fileobj=outfile,
          dcPath=filepath,
          offset=offset,
          length=length,
          tth=tth,
          priority=priority,
          filelist=filelist
        )
        self.tryGet()
        return self.currentTransfer.deferred

    def getFileListName(self):
        if "XmlBZList" in self.remoteSupports:
            return "files.xml.bz2"
        elif "BZList" in self.remoteSupports:
            return "MyList.bz2"
        return "MyList.DcLst"
    
    def getFileList(self, outfile, priority=0):
        return self.getFile(outfile, self.getFileListName(), filelist=True, priority=priority)
    
    def getPartialFileList(self, outfile, path):
        self.currentTransfer = Transfer(
          'upload',
          filelist=True,
          fileobj=outfile,
          dcPath=path,
        )
        self.sendAndWait("$ADCGET list %s" % (path.encode('utf-8'),))
        return self.currentTransfer.deferred

    def tryGet(self):
        assert self.currentTransfer
        if "ADCGet" in self.remoteSupports and self.currentTransfer.tth and len(self.currentTransfer.tth) == 39:
            self.sendAndWait("$ADCGET file TTH/%s %d %d" % (str(self.currentTransfer.tth), self.currentTransfer.offset, self.currentTransfer.length,))
        elif "ADCGet" in self.remoteSupports and self.currentTransfer.dcPath == 'files.xml.bz2':
            self.sendAndWait("$ADCGET file files.xml.bz2 0 -1")
        elif "XmlBZList" in self.remoteSupports and self.currentTransfer.length == -1 and self.currentTransfer.dcPath != 'files.xml.bz2':
            self.sendAndWait("$UGetBlock %d %d %s" % (self.currentTransfer.offset, self.currentTransfer.length, self.currentTransfer.dcPath.encode('utf-8'),))
        else:
            self.sendAndWait("$Get %s$%s" % (self.currentTransfer.dcPath.encode(DC_ENCODING), self.currentTransfer.offset+1,))

    def handleFailed(self, reason):
        # reply to UGetBlock
        assert self.currentTransfer

        dl, dd = self.downloadCleanup(True)
        err = Exception(reason)
        dd.errback(err)  
    
    def handleSending(self, fileLength):
        # reply to UGetBlock
        self.currentTransfer.bytesToTransfer = int(fileLength)
        self.startDownload()

    def handleCSND(self, data):
        #data, filedata = data.split('\n', 1)
        self.handleADCSND(data)      
        # we have to add the delimiter to the end as that was stripped off thinking this was a DC 
        # command
        #self.rawDataReceived(filedata + self.delimiter)
    def handleADCSND(self, data):
        # reply to ADCGET
        # $ADCSND file TTH/PPUROLR2WSYTGPLCM3KV4V6LJC36SCTFQJFDJKA 0 12345
        sndType, tth, offset, length = data.split(' ', 3)
        if sndType == 'tthl' and not self.currentTransfer.leaves:
            raise Exception('peer tried to send file when I was asking for the leaves')
        self.currentTransfer.bytesToTransfer = int(length)
        self.startDownload()

    def handleFileLength(self, fileLength):
        self.currentTransfer.bytesToTransfer = int(fileLength)
        self.sendLine("$Send")
        self.startDownload()

    def startDownload(self):
        louie.send('peer:download:start', self, id(self), self.currentTransfer.dcPath, *self.currentTransfer.status())
        self.currentTransfer.start()
        self.lastTimeFiredEvent = time.time()
        self.setRawMode()

    def rawDataReceived(self, data):
        self.resetTimeout()
        self.currentTransfer.write(data)
        if time.time() - self.lastTimeFiredEvent > 0.25:
            louie.send('peer:download:progress', self, id(self), *self.currentTransfer.status())
            self.lastTimeFiredEvent = time.time()
        if self.currentTransfer.isDone():
            bytesToTransfer, bytesTransfered, rate = self.currentTransfer.status()
            tr, dd = self.downloadCleanup()    
            dd.callback(tr.rate)
            louie.send('peer:download:end', self, id(self), bytesToTransfer, bytesTransfered, rate)
            self.setLineMode()

    def downloadCleanup(self, error=False):
        dd = self.currentTransfer.deferred
        del self.currentTransfer.deferred
        self.currentTransfer.flush()
        tr = self.currentTransfer
        self.currentTransfer = None
        if error:
            kwargs = dict(error=True)
            louie.send('peer:download:end', self, id(self), *tr.status(), **kwargs)
        self.setStatus('idle')
        return tr, dd
    
    # upload stuff

    def createTransfer(self, ret):
        self.currentTransfer = Transfer('upload', **ret)
        return self.currentTransfer
    
    def getSlot(self):
        if self.hasSlot:
            return self.hasSlot
        try:
            self.peerHerder.takeASlot(self.peer)
            self.hasSlot = True
            return self.hasSlot
        except errors.MaxedOutError, ee:
            self.sendLine('$MaxedOut %d' % (ee.args[0],))
            self.transport.loseConnection()
        return False
    
    def handleGet(self, data):
        if not self.getSlot():
            return
        filepath, offset = data.split("$", 1)
        offset = int(offset) - 1
        dd = self.fileSource.getByPath(filepath.decode(DC_ENCODING))
        def _sendIt(transfer):
            if not transfer:
                return
            transfer.offset = offset
            self.sendLine("$FileLength %s" % (transfer.length,))
            # now we wait for $Send
        dd.addCallbacks(self.createTransfer, self.fileNotAvailable)
        dd.addCallback(_sendIt)
    def handleSend(self, data):
        self.sendOutgoingFile()

    def handleUGetBlock(self, data):
        if not self.getSlot():
            return
        offset, blockSize, filepath = data.split(" ", 2)
        offset = int(offset)
        blockSize = int(blockSize)
        if filepath == 'files.xml.bz2':
            dd = self.fileSource.getFilesXmlBz2(filter=self.hub.filter)
        else:
            dd = self.fileSource.getByPath(filepath.decode('utf-8'))
        def _sendIt(transfer):
            if not transfer:
                return
            if (transfer.length - offset != blockSize) and blockSize != -1:
                raise NotImplementedError("size: %s, offset: %s, blockSize: %s" % (transfer.length, offset, blockSize,))
            transfer.offset = offset
            self.sendLine("$Sending %d" % (transfer.length,))
            self.sendOutgoingFile()
        dd.addCallbacks(self.createTransfer, self.fileNotAvailable)
        dd.addCallback(_sendIt)

    def handleADCGET(self, data):
        if not self.getSlot():
            return
        getType, hash, offset, bytesToTransfer = data.split(' ', 3)
        if getType == 'list' and hash != '/':
            self.sendLine("$Error File Not Available")
            self.transport.loseConnection()
            return
        offset = int(offset)
        if ' ' in bytesToTransfer:
            bytesToTransfer, junk = bytesToTransfer.split(' ', 1)
        bytesToTransfer = int(bytesToTransfer)
        if getType == 'file' and hash == 'files.xml.bz2':
            dd = self.fileSource.getFilesXmlBz2(filter=self.hub.filter)
        elif getType == 'list' and hash == '/':
            dd = self.fileSource.getFilesXmlBz2(filter=self.hub.filter)
        elif getType == 'file':
            if not hash.startswith('TTH/'):
                raise NotImplementedError('do not support other hash types')
            dd = self.fileSource.getByTTH(hash[4:])
        elif getType == 'tthl':
            dd = self.fileSource.getLeavesForTTH(hash[4:])
        else:
            raise NotImplementedError('do not support other get types')
        def _sendIt(res):
            self.log('sending %r' % res['dcPath'])
            transfer = self.createTransfer(res)
            if transfer is None:
                return
            try:
                if bytesToTransfer != -1:
                    transfer.bytesToTransfer = bytesToTransfer
                transfer.offset = offset
                self.sendLine("$ADCSND %s %s %s %s" % (getType, hash, offset, transfer.bytesToTransfer,))
                self.sendOutgoingFile()
            except Exception, ee:
                print ee
                raise
        dd.addCallbacks(_sendIt, self.fileNotAvailable)
            
    def sendOutgoingFile(self):
        self.setStatus('uploading')
        self.currentTransfer.start()
        louie.send('peer:upload:start', self, id(self), self.currentTransfer.dcPath, *self.currentTransfer.status())
        def _(data):
            louie.send('peer:upload:progress', self, id(self), *self.currentTransfer.status())
            self.resetTimeout()
            return data
        sender = basic.FileSender()
        dd = sender.beginFileTransfer(self.currentTransfer, self.transport, transform=_)
        dd.addCallbacks(self.uploadDone, log.err)

    def fileNotAvailable(self, failure):
        failure.trap(errors.FileNotAvailableError)
        self.sendLine("$Error File Not Available")

    def uploadDone(self, res):
        self.setStatus('idle')
        louie.send('peer:upload:end', self, id(self), *self.currentTransfer.status())
        self.currentTransfer.close()
        self.currentTransfer = None
            
class PeerServerFactory(protocol.Factory):
    def __init__(self, application, protocol=PeerProtocol):
        self.application = application
        self.listeningPort = None # set after this factory is given a listeningPort
        self.protocol = protocol
        self.expectedPeers = []

    def expectPeer(self, peer):
        if len(self.expectedPeers) == 0:
            self.listeningPort.startListening()
        self.expectedPeers.append(peer)

    def gotConnectionFromNick(self, nick):
        for peer in self.expectedPeers:
            if peer.nick == nick:
               self.expectedPeers.remove(peer)
               if len(self.expectedPeers) == 0:
                   self.listeningPort.stopListening()
               return peer
        raise UnexpectedConnectionError, "We were not expecting a connection from %r" % (nick,)
        
    def buildProtocol(self, addr):
        pp = self.protocol(connecting=False, application=self.application)
        pp.factory = self
        return pp

class Transfer(object):
    def __init__(self, transferType, fileobj, dcPath=None, offset=0, length=-1, tth=None, filelist=False, leaves=False, priority=0):
        self.type = transferType
        self.fileobj = fileobj

        self.dcPath = dcPath
        self._offset = offset
        self.length = length
        self.tth = tth
        self.filelist = filelist
        self.leaves = leaves
        self.priority = priority
      
        self.deferred = defer.Deferred()
        self.startTime = None
        self.bytesToTransfer = self.length
        self.bytesLeft = self.bytesToTransfer
        self.currentRate = 0
        
        self.lastTimeComputed = None
        self.bytesInLastSecond = 0
      
    def __repr__(self):
        return "<%s dict:%r>" % (self.__class__, self.__dict__)
      
    def _getOffset(self):
        return self._offset
    def _setOffset(self, offset):
        self._offset = offset
        #self.bytesToTransfer -= self._offset
        self.fileobj.seek(self._offset)
    offset = property(_getOffset, _setOffset)
    
    def start(self):
        self.startTime = self.lastTimeComputed = time.time()
        assert self.startTime, "%r" % (self,)
        self.bytesLeft = self.bytesToTransfer
        if callable(self.fileobj):
            self.fileobj = self.fileobj()
        self.fileobj.seek(self.offset)

    def transfered(self, byteCount):
        assert self.startTime, "%r" % (self,)
        self.bytesLeft -= byteCount
        now = time.time()
        self.bytesInLastSecond += byteCount
        if (now - self.lastTimeComputed) > 1:
            self.currentRate = self.bytesInLastSecond/float(now - self.lastTimeComputed)
            self.bytesInLastSecond = 0
            self.lastTimeComputed = now

    @property
    def bytesTransfered(self):
        return self.bytesToTransfer - self.bytesLeft
    
    @property
    def rate(self):
        return self.currentRate
        
    def status(self):
        return (self.bytesToTransfer, self.bytesTransfered, self.rate,)
    
    def write(self, data):
        self.fileobj.write(data)
        self.transfered(len(data))

    def read(self, size):
        try:
            if size > self.bytesLeft:
                size = self.bytesLeft
            data = self.fileobj.read(size)
            self.transfered(len(data))
            return data
        except Exception, ee:
            print ee
            raise

    def close(self):
        self.fileobj.close()
    def flush(self):
        if hasattr(self.fileobj, 'flush'):
            self.fileobj.flush()
                
    def isDone(self):
        if self.bytesLeft == 0:
            return True
        return False

class Peer(object):
    # TODO: make immutable
    instances = []

    def _removeRef(cls, instanceRef):
        cls.instances.remove(instanceRef)
    
    _removeRef = classmethod(_removeRef)
    
    def __new__(cls, nick, hubId=None):
        if not hubId:
            assert '$' in nick, nick
            nick, hubId = nick.split('$', 1)
        if type(nick) is not unicode:
            nick = unicode(nick, DC_ENCODING)
        if isinstance(hubId, tuple):
            raise Exception, "can't deal with hubAddrs anymore"
        
        for peerRef in cls.instances:
            ii = peerRef()
            if ii.nick == nick and ii.hubId == hubId:
                return ii
        self = object.__new__(cls)
        cls.instances.append(weakref.ref(self, cls._removeRef))
        return self
    
    def __init__(self, nick, hubId=None):
        if not hubId:
            assert '$' in nick, nick
            nick, hubId = nick.split('$', 1)
        # yes you have to convert this both in __new__ and in __init__
        if type(nick) is not unicode:
            nick = unicode(nick, DC_ENCODING)
        assert nick, "nick is %r" % (nick,)
        self.nick = nick
        if isinstance(hubId, tuple):
            raise Exception, "can't deal with hubAddrs anymore"
        self.hubId = hubId

    def __str__(self):
        return self.__unicode__().encode('utf-8')

    def __unicode__(self):
        return u"%s$%s" % (self.nick, self.hubId) 
    
    def __repr__(self):
        return "<%s %r %s at %#x>" % (self.__class__.__name__, self.nick, self.hubId, id(self),) 

    def __getnewargs__(self):
        return (self.nick, self.hubId,)

class UnexpectedConnectionError(StandardError):
    pass
    