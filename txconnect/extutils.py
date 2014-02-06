import os
from twisted.application import service
from twisted.internet import defer

from zope.interface import implements

from directconnect.interfaces import IHasher, IDirLister
from workerpool.workerpool import WorkerPool

class ExtUtilsService(service.Service):
    name = 'extutils'
    implements(IHasher, IDirLister)
    
    def __init__(self):
        self.workerPool = None

    def tthFile(self, filepath):
        return self.workerPool.sendCmd('tth_file', filepath.path)
    
    def neededBlocks(self, filepath, root, leaves):
        return self.workerPool.sendCmd('needed_blocks', filepath.path, root, leaves)

    def listDir(self, dirpath):
        return self.workerPool.sendCmd('list_dir', dirpath.path)

    def startService(self):
        self.workerPool = WorkerPool(os.path.abspath(os.path.join(__file__, '../indexer_util.py')))
        service.Service.startService(self)
        
    @defer.inlineCallbacks
    def stopService(self):
        yield self.workerPool.stop()
        yield service.Service.stopService(self)
