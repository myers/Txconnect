import pickle, struct

from twisted.internet import protocol, reactor, defer

class WorkerPool(object):
    def __init__(self, targetFile):
        self.protocols = []
        self.queue = []
        self.maxProcesses = 2
        self.targetFile = targetFile
   
    def findOrCreateIdleProcess(self):
        target = None
        for pp in self.protocols:
            if pp.isIdle():
                target = pp
                break
        if not target and len(self.protocols) < self.maxProcesses:
            target = PickleCommandProcess()
            command = ['/usr/bin/python', self.targetFile]
            reactor.spawnProcess(target, command[0], command, env=None)
            self.protocols.append(target)
        return target
        
    # FIXME not doing the right thing with errors
    def checkQueue(self, res):
        self.runQueue()
        return res

    def runQueue(self):
        if len(self.queue) == 0:
            return
        target = self.findOrCreateIdleProcess()
        if not target:
            return
        deferred, args = self.queue.pop(0)
        target.callCommand(deferred, *args)
        
    def sendCmd(self, *args):
        deferred = defer.Deferred()
        deferred.addCallbacks(self.checkQueue, self.checkQueue)
        target = self.findOrCreateIdleProcess()
        if target:
            target.callCommand(deferred, *args)
        else:
            #assert len(self.queue) < 100
            self.queue.append((deferred, args,))
        return deferred
    
    def stop(self):
        return defer.DeferredList([pp.stop() for pp in self.protocols])

class PickleCommandProcess(protocol.ProcessProtocol):
    def __init__(self):
        self.currentCommand = None
        self.resultsDeferred = None
        self._buffer = ''
        self.stopDeferred = None
    
    def stop(self):
        self.stopDeferred = defer.Deferred()
        dd = defer.Deferred()
        self.callCommand(dd, 'quit')
        def _(res):
            self.transport.loseConnection()
        dd.addCallback(_)
        return self.stopDeferred

    def processEnded(self, status):
        if self.stopDeferred:
            self.stopDeferred.callback(status)        
        
    def isIdle(self):
        return self.resultsDeferred == None
    
    def sendLine(self, payload):
        payload = struct.pack('!I', len(payload)) + payload
        #print "sending %r to %d" % (payload, self.transport.pid,)
        self.transport.write(payload)

    def connectionMade(self):
        #print "%r connection made %r %r" % (self, self.transport, self.currentCommand,)
        if self.currentCommand:
            self.sendLine(self.currentCommand)
        
    def callCommand(self, deferred, method, *args):
        assert self.currentCommand is None
        self.currentCommand = pickle.dumps(dict(method=method, args=args), pickle.HIGHEST_PROTOCOL)
        self.resultsDeferred = deferred
        #print "%r %r %r" % (self, self.transport, self.currentCommand,)
        if self.transport:
            self.sendLine(self.currentCommand)
                            
    def errReceived(self, data):
        print "err: %r" % (data,)   
        
    def outReceived(self, data):
        self._buffer = self._buffer + data
        prefixSize = struct.calcsize('!I')
        if len(self._buffer) < prefixSize:
            #print 'too small'
            return
        totalSize = struct.unpack('!I', self._buffer[:prefixSize])[0] + prefixSize
        if len(self._buffer) < totalSize:
            #print 'too small for size'
            return    
        #print "%r" % (self._buffer[prefixSize:totalSize],)
        res = pickle.loads(self._buffer[prefixSize:totalSize])
        self._buffer = self._buffer[totalSize:]
        #print res
        dd = self.resultsDeferred
        self.currentCommand = None
        self.resultsDeferred = None
        if res.has_key('result'):
            dd.callback(res['result'])
        else:
            dd.errback(res['exception'])
