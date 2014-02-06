import traceback, time, os

import louie
from .. import tth, dbthread, statsutil
from twisted.internet import reactor, defer
from twisted.python import log
from twisted.python.filepath import FilePath, UnlistableError

from . import models

class Indexer(object):
    def __init__(self, sharestore):
        self.sharestore = sharestore
        self.queueFileSize = 0
        # FIXME this seems to get way off while indexing 373,771 / 373,335
        self.fileCount = 0
        self.skippedFileCount = 0
        self.running = False
        # k: path, v: deferred
        self.filesToBeHashed = {}
        self.hashingAverage = statsutil.WeightedAvg(100)

    def log(self, msg):
        log.msg(msg, system='Indexer')

    @property
    def hasher(self):
        return self.sharestore.hasher
    @property
    def dirLister(self):
        return self.sharestore.dirLister
    
    @defer.inlineCallbacks
    def start(self):
        if self.running:
            raise Exception('already running')
        self.running = True

        louie.send('share_store:indexer:started')
        self.log('starting')
        yield self.run()
        self.shutdown()
        
    def shutdown(self):
        self.running = False
        self.log('finished')
        louie.send('share_store:indexer:finished')

    @defer.inlineCallbacks
    def run(self):
        self.log('deleteNotInRoots')
        yield self.deleteNotInRoots()
        indexedDirs = yield dbthread.runReadQuery(models.Path.objects.indexed_directories)
        for rootFilepath in self.sharestore.roots.values():
            if rootFilepath not in indexedDirs.keys():
                self.log('Adding new root dir %r' % (rootFilepath,))
                indexedDirs[rootFilepath] = yield dbthread.runWriteQuery(self.sharestore._addDirectoryPath, rootFilepath)

        toDelete = []
        while indexedDirs:
            if not self.running: break

            dirFilepath, directory = indexedDirs.popitem()
            assert directory
            assert type(directory.filepath.path) is unicode, directory.filepath
            self.log('Now in %r' % (directory.filepath.path,))
            if not dirFilepath.isdir():
                toDelete.append(directory)
                continue

            louie.send('share_store:walking', currentDirectory=dirFilepath.path, fileCount=self.fileCount, skipped=self.skippedFileCount)

            @dbthread.readQuery
            def _checkIfUpToDate():
                if directory.up_to_date():
                    fileCount = directory.file_set.exclude(filetype=8).count()
                    self.skippedFileCount += fileCount
                    self.fileCount += fileCount
                    return True
                return False
            upToDate = yield _checkIfUpToDate()
            if upToDate:
                continue

            yield self.visitDir(directory, indexedDirs)
            
        @dbthread.writeQuery
        def _deleteMissingDirectories():
            for directory in toDelete:
                models.Path.objects._delete_dir(directory)
        yield _deleteMissingDirectories()
        louie.send('share_store:walking:done', fileCount=self.fileCount)
        if self.filesToBeHashed:
            yield defer.DeferredList(self.filesToBeHashed.values())
        
    @dbthread.writeQuery
    def deleteNotInRoots(self):
        models.Path.objects.delete_not_in_roots()

    @defer.inlineCallbacks
    def listDir(self, filepath):
        entries = yield self.dirLister.listDir(filepath)
        def utf8check(string):
            try:
                string.decode('utf-8')
                return True
            except UnicodeDecodeError:
                return False
        defer.returnValue([FakeFilePath(filepath.path, entry) for entry in entries if utf8check(entry['name'])])
        
    def addToHashQueue(self, filepath, directory):
        dd = self.hasher.tthFile(filepath)
        dd.addCallback(self.addFile, filepath, directory)
        self.filesToBeHashed[filepath.path] = dd
        self.queueFileSize += filepath.getsize()
        louie.send('share_store:hashing', self, 
          fileBeingHashed=filepath.path, 
          filesToBeHash=len(self.filesToBeHashed), 
          sizeToBeHash=self.queueFileSize)
        return dd

    # FIXME: can this go away and use sharedstores addFile?
    def addFile(self, res, filepath, directory):
        tthRoot, tthLeaves, elapsed = res
        del self.filesToBeHashed[filepath.path]
        rate = self.hashingAverage.add(filepath.getsize()/elapsed)
        self.queueFileSize -= filepath.getsize()
        louie.send('share_store:hashed', self, 
          fileBeingHashed=filepath.path, 
          filesToBeHash=len(self.filesToBeHashed), 
          sizeToBeHash=self.queueFileSize,
          rate=rate)
        return self.sharestore._add3(tthRoot, tthLeaves, filepath, directory)
        
    @defer.inlineCallbacks
    def visitDir(self, directory, indexedDirs):
        filesSentToBeHashed = False
        pendingHashes = []
        #print 'visiting %r' % directory.filepath
        @dbthread.readQuery
        def _getIndexedFiles():
            return dict([(ff.filepath.path, ff) for ff in models.Path.objects.filter(directory=directory).exclude(filetype=8)])
        indexedFiles = yield _getIndexedFiles()
        
        children = yield self.listDir(directory.filepath)
        for entry in children:
            if not models.shouldIndexFilepath(entry):
                continue
            if entry.isdir():
                if entry not in indexedDirs.keys():
                    indexedDirs[entry] = yield dbthread.runWriteQuery(self.sharestore._addDirectoryPath, entry)
                continue
            self.fileCount += 1

            indexedFile = None
            if indexedFiles.has_key(entry.path):
                indexedFile = indexedFiles.pop(entry.path)
                if indexedFile.up_to_date(entry.getModificationTime()):
                    self.skippedFileCount += 1
                    continue
                else:
                    log.msg("%r not uptodate: db %r vs fs %r" % (indexedFile.filepath.path, indexedFile.mtime, indexedFile.current_mtime(),))

            pendingHashes.append(self.addToHashQueue(entry, directory))
        
        fileChildren = [cc for cc in children if models.shouldIndexFilepath(cc) and not cc.isdir()]
        
        @dbthread.writeQuery
        def _deleteMissingFiles():
            models.Path.objects.delete_paths(indexedFiles)

        if len(indexedFiles):
            yield _deleteMissingFiles()
        
        @dbthread.writeQuery
        def _markUpToDate(*args):
            try:
                directory.mark_up_to_date(True, filelist=fileChildren)
            except UnlistableError:
                directory.delete()
        if len(pendingHashes) == 0:
            yield _markUpToDate()
        else:
            dl = defer.DeferredList(pendingHashes)
            dl.addCallback(_markUpToDate)
    
class FakeFilePath:
    def __init__(self, dirpath, entry):
        self.entry = entry
        self.path = os.path.join(dirpath, entry['name'].decode('utf8'))

    def exists(self):
        return True
        
    def getModificationTime(self):
        return self.entry['mtime']
            
    def getsize(self):
        return self.entry['size']
    
    def isdir(self):
        return self.entry['type'] == 'd'
        
    def isfile(self):
        return self.entry['type'] == 'f'

    def basename(self):
        return self.entry['name']

    def segmentsFrom(self, ancestor):
        return FilePath(self.path).segmentsFrom(ancestor)
                
    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, self.path,)

# two threads
# thread 1
# get list of all directories we have indexed before
# for each root
# for root, dirs, files in os.walk(root)
#    is root in dirs?
#    no make dir record, add all files on to hash queue
#    get {filename: (size, mtime,)} from database for root
#    for files
#      is it in our list ?
#      no? put on hash queue
#      yes but different, put on hash queue
#      yes same, do nothing
#      remove from list of files from db
#   remove remaing files from db that we have
#   remove root from list of directories from database
# remove directories remaing on list

# thread 2

