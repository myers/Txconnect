import datetime

from twisted.python import log
from twisted.application import service
from twisted.internet import defer, reactor

#from zope.interface import implements
import louie

from .. import service_util, dbthread
from . import models

class TrafficLogger(service.Service, service_util.ServiceUtil):
    name = 'trafficLogger'    

    def __init__(self, locator):
        self.locator = locator
        self.entries = {}
        self.shutdownDeferred = None

    def startService(self):
        service.Service.startService(self)
        #louie.connect(self.onPeerTransferStart, 'peer:download:start')
        #louie.connect(self.onPeerTransferStart, 'peer:upload:start')

        #louie.connect(self.onPeerTransferEnd, 'peer:download:end')
        #louie.connect(self.onPeerTransferEnd, 'peer:upload:end')
    
    def stopService(self):
        service.Service.stopService(self)
        if not self.entries:
            self._cleanUp()
            return
          
        self.shutdownDeferred = defer.Deferred()
        def _timeout():
            self.log('timed out waiting for all transfers to end: %r' % (self.entries,))
            self.shutdownDeferred.errback(TimeoutError)
        dc = reactor.callLater(15, _timeout)
        
        def _afterEmpty(res):
            self.log('successfully waited for all transfers to stop')
            dc.cancel()
            self._cleanUp()
            return res
        self.shutdownDeferred.addCallback(_afterEmpty)
        return self.shutdownDeferred

    def _cleanUp(self):
        louie.disconnect(self.onPeerTransferStart, 'peer:download:start')
        louie.disconnect(self.onPeerTransferStart, 'peer:upload:start')

        louie.disconnect(self.onPeerTransferEnd, 'peer:download:end')
        louie.disconnect(self.onPeerTransferEnd, 'peer:upload:end')
            
    def onPeerTransferStart(self, connectionId, path, bytesToTransfer, bytesTransfered, rate, sender=None, signal=None):
        if 'upload' in signal:
            t_type = 'U'
        else:
            t_type = 'D'
        entry = models.LogEntry(
          type=t_type,
          peer=sender.peer,
          path=path,
          tth=sender.currentTransfer.tth,
          priority=sender.currentTransfer.priority,
          offset=sender.currentTransfer.offset,
          requested_length=bytesToTransfer
        )
        self.entries[connectionId] = entry
        self._saveEntry(entry)

    def onPeerTransferEnd(self, connectionId, bytesToTransfer, bytesTransfered, rate, sender=None):
        entry = self.entries.pop(connectionId, None)
        if entry is None:
            self.log('no entry found during onPeerTransferEnd %r' % (connectionId,))
            return
        entry.actual_length = bytesTransfered
        entry.end = datetime.datetime.now()
        dd = self._saveEntry(entry)
        def _after(res):
            if len(self.entries) == 0 and self.shutdownDeferred:
                self.shutdownDeferred.callback(True)
        dd.addCallbacks(_after, log.err)
    
    @dbthread.writeTrafficLogQuery
    def _saveEntry(self, entry):
        entry.save()

class TimeoutError(StandardError):
    pass
    
