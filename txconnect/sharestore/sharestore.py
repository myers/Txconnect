import base64, os, bz2, ntpath, StringIO, mimetypes, datetime
from xml.sax.saxutils import quoteattr

import louie 

from django.core.exceptions import ObjectDoesNotExist

from ..directconnect import errors, interfaces
from .. import directconnect

from twisted.python import log
from twisted.internet import reactor, defer, threads
from twisted.application import service
from twisted.python.filepath import FilePath
from zope.interface import implements

from .. import dbthread

from . import models, indexer

class ShareStore(service.Service):
    implements(interfaces.IFileSource)
    
    """
    roots = dict(str=Filepath)
    """
    def __init__(self, locator):
        self.locator = locator
        
        roots = self.config['files']['shared']
        for key in roots.keys():
            if isinstance(roots[key], basestring):
                roots[key] = FilePath(os.path.expanduser(roots[key].decode('utf-8')))
        self.roots = roots
        models.Path.roots = roots
        self.size = 0
        self.count = 0
        self.updateSizeDelayedCall = None
        self.setupDone = defer.Deferred()
        self.sizeChanged()

        louie.connect(self.onDownloadFinished, 'download:finished')
        self._filelistDeferred = None

    def filesXmlBz2(self, filter=None):
        if filter is None:
            return self.config.dataDir.child('files.xml.bz2')
        else:
            return self.config.dataDir.child('files.' + '+'.join(filter) + '.xml.bz2')

    def outOfDateFilesXmlBz2(self, filter=None):
        if filter is None:
            return self.config.dataDir.child('files.outofdate.xml.bz2')
        else:
            return self.config.dataDir.child('files.' + '+'.join(filter) + '.outofdate.xml.bz2')
        
    def startService(self):
        service.Service.startService(self)

    @defer.inlineCallbacks
    def stopService(self):
        louie.disconnect(self.onDownloadFinished, 'download:finished')
        if self.updateSizeDelayedCall and self.updateSizeDelayedCall.active():
            self.updateSizeDelayedCall.cancel()
            self.updateSizeDelayedCall = None
        yield service.Service.stopService(self)
    
    @property
    def config(self):
        return interfaces.IConfig(self.locator)
    @property
    def hasher(self):
        return interfaces.IHasher(self.locator)
    @property
    def dirLister(self):
        return interfaces.IDirLister(self.locator)

    def log(self, msg):
        log.msg(msg, system='ShareStore')
        
    def onDownloadFinished(self, download, **kwargs):
        if download.type != 'file':
            return
        dd = self.add(FilePath(download.outfilepath))
        dd.addCallback(lambda res: self.invalidateFilesXmlBz2())
        return dd # need to return this for a test

    def search(self, term, maxsize=None, minsize=None, filetype=1, filter=None):
        if maxsize and minsize:
            raise Exception('cannot have both maxsize and minsize')
        self.log('searching for %r %r' % (term, filetype,))
        expires = datetime.datetime.now() + datetime.timedelta(seconds=30)
        if filetype == 9:
            return self._searchTTH(term, expires, filter)
        @dbthread.searchQuery
        def _doSearch(term=term):
            if datetime.datetime.now() > expires:
                self.log('Query was too old by the time we ran it %r' % ((datetime.datetime.now() - expires),))
                return []
            return models.Path.objects.search(term, maxsize, minsize, filetype, filter)
            
        return _doSearch()
    
    @dbthread.searchQuery
    def _searchTTH(self, tth, expires, filter=None):
        if datetime.datetime.now() > expires:
            self.log('Query was too old by the time we ran it %r' % ((datetime.datetime.now() - expires),))
            return []
        return models.Path.objects.search_tth(tth, filter)
        
    @dbthread.readQuery
    def getByPath(self, dcPath):
        try:
            path = models.Path.objects.get(path=dcPath)
            return self._infoForPath(path)
        except (ObjectDoesNotExist, KeyError,):
            raise errors.FileNotAvailableError
        except IOError, ee:
            if ee.errno == 2:
                raise errors.FileNotAvailableError

    @dbthread.readQuery
    def getByTTH(self, tth):
        try:
            path = models.Path.objects.filter(tth=tth)[0]
            return self._infoForPath(path)
        except (ObjectDoesNotExist, IndexError,):
            raise errors.FileNotAvailableError
        except IOError, ee:
            if ee.errno == 2:
                raise errors.FileNotAvailableError

    @dbthread.readQuery
    def haveFileWithTTH(self, tth):
        try:
            path = models.Path.objects.filter(tth=tth)[0]
            return path.filepath
        except (ObjectDoesNotExist, IndexError):
            return None

    @dbthread.readQuery
    def getLeavesForTTH(self, tth):
        try:
            path = models.Path.objects.filter(tth=tth)[0]
            hl = models.HashLeaves.objects.get(tth=tth)
            fileobj = StringIO.StringIO(hl.leaves)
        except IndexError, ee:
            print ee
            raise errors.FileNotAvailableError
        except models.HashLeaves.DoesNotExist, ee:
            fileobj = StringIO.StringIO(base64.b32decode(tth+'='))
        return dict(
          leaves=True,
          fileobj=fileobj,
          length=len(fileobj.getvalue()),
          tth=tth,
          dcPath=path.path
        )

    def _infoForPath(self, sharedFile):
        return dict(
          fileobj=sharedFile.filepath.open(),
          length=sharedFile.size,
          tth=sharedFile.tth,
          dcPath=sharedFile.path
        )

    def startIndexer(self):
        self.indexer = indexer.Indexer(self)
        dd = self.indexer.start()
        dd.addCallback(lambda res: self.invalidateFilesXmlBz2())
        return dd
    
    def sizeChanged(self):
        # if we think we have no files (like when we first startup) run this immediatly 
        if self.count == 0:
            self._updateSize()
            return
        if self.updateSizeDelayedCall:
            return
        self.updateSizeDelayedCall = reactor.callLater(30, self._updateSize)
            
    def _updateSize(self):
        if self.updateSizeDelayedCall and self.updateSizeDelayedCall.active():
            self.updateSizeDelayedCall.cancel()
            self.updateSizeDelayedCall = None
        dd = dbthread.runReadQuery(models.Path.objects.size_and_count)
        def _afterWeHaveSize(res):
            self.size, self.count = res
            if not self.setupDone.called:
                self.log('setup done')
                self.setupDone.callback(True)
            louie.send('share_store:size', self, size=self.size, count=self.count)
        dd.addCallbacks(_afterWeHaveSize, log.err)
            

    def add(self, filepath):
        self.log("adding %r to store" % (filepath,))
        if not filepath.isfile():
            raise StandardError('tried to add a non file to the store: %r' % (filepath,))
        results = defer.Deferred()
        dd = self.hasher.tthFile(filepath)
        dd.addCallback(self._add2, filepath, results)
        return results
    
    def _add2(self, res, filepath, results=None):
        tthRoot, tthLeaves, elapsed = res
        def _(shared_file):
            if results:
                results.callback(shared_file)
        
        dd = self._add3(tthRoot, tthLeaves, filepath)
        dd.addCallbacks(_, log.err)

    @dbthread.writeQuery
    def _add3(self, tthRoot, tthLeaves, filepath, directory=None):
        try:
            return self._add4(tthRoot, tthLeaves, filepath, directory)
        except NotInShareRootsError, ee:
            log.msg(ee.args)
        except UnicodeDecodeError, ee:
            log.err("filepath with error: %r: %r" % (filepath, ee,))
        except Exception, ee:
            print "%r" % (ee,)
            import traceback
            traceback.print_exc()
            raise
        return None

    def _dcPathPartsFor(self, filepath):
        if type(filepath.path) is str:
            filepath.path = filepath.path.decode('utf-8')
        root = [root for root, rootFilePath in self.roots.items() if filepath.path.startswith(rootFilePath.path)]
        if not root:
            raise NotInShareRootsError('adding a file that not in a shared root: %r' % (filepath,))
        root = root[0]#.decode('utf-8')
        
        pathParts = [root]
        if self.roots[root] != filepath:
            #filepath.path = filepath.path.decode('utf-8')
            pathParts.extend(filepath.segmentsFrom(self.roots[root]))
        for part in pathParts:
            if '\\' in part:
                raise Exception("adding a file with '\' in it's path")
        return pathParts

    def _addDirectoryPath(self, filepath):
        pathParts = self._dcPathPartsFor(filepath)
        dirDcPathParts = []
        dirPath = None
        for part in pathParts:
            dirDcPathParts.append(part)
            dirPath, created = models.Path.objects.get_or_create(
              path=ntpath.sep.join(dirDcPathParts), 
              filetype=8,
              directory=dirPath,
            )
        return dirPath
              
    def _add4(self, tthRoot, tthLeaves, filepath, dirPath=None):
        if dirPath is None:
            dirPath = self._addDirectoryPath(filepath.parent())
        fileDcPath = ntpath.sep.join(self._dcPathPartsFor(filepath))
        path, pathCreated = models.Path.objects.get_or_create(
          path=fileDcPath, 
          filetype=self._getPathFileTypeFromFilename(fileDcPath), 
          directory=dirPath,
          defaults=dict(
            tth=tthRoot
          )
        )
        if path.tth != tthRoot:
            path.tth = tthRoot
            path.save()
        leaves = tthLeaves
        if leaves:
            hl, created = models.HashLeaves.objects.get_or_create(
              tth=tthRoot,
              defaults=dict(
                leaves=leaves
              )
            )
        if pathCreated:
            reactor.callFromThread(louie.send, 'share_store:new_file', self, path=filepath)
            reactor.callFromThread(self.sizeChanged)
        return path

    def _getPathFileTypeFromFilename(self, filename):
        mimetype = mimetypes.guess_type(filename)[0]
        if mimetype is None:
            return 4
        elif mimetype.startswith('audio'):
            return 2
        elif mimetype in ('application/zip', 'application/rar', 'application/x-rar-compressed',):
            return 3
        elif mimetype in ('application/x-msdos-program', 'application/x-msdownload'):
            return 5
        elif mimetype.startswith('image'):
            return 6
        elif mimetype.startswith('video'):
            return 7
        return 4

    # FIXME: invalidate all filelists
    def invalidateFilesXmlBz2(self):
        self.filesXmlBz2().restat(reraise=False)
        self.outOfDateFilesXmlBz2().restat(reraise=False)
        if self.filesXmlBz2().exists() and self.outOfDateFilesXmlBz2().exists():
            self.outOfDateFilesXmlBz2().remove()
        if self.filesXmlBz2().exists() and not self.outOfDateFilesXmlBz2().exists():
            self.filesXmlBz2().moveTo(self.outOfDateFilesXmlBz2())

    def _infoForFilesXmlBz2(self, filelist):
        return dict(
          filelist=True,
          fileobj=filelist.open('rb'),
          length=filelist.getsize(),
          tth=None,
          dcPath='files.xml.bz2'
        )
    
    def getFilesXmlBz2(self, filter=None):
        self.log("getFilesXmlBz2 with filter %r" % (filter,))
        self.filesXmlBz2(filter).restat(reraise=False)
        self.outOfDateFilesXmlBz2(filter).restat(reraise=False)
        if self.filesXmlBz2(filter).exists():
            return defer.succeed(self._infoForFilesXmlBz2(self.filesXmlBz2(filter)))

        ret = self._createFilesXmlBz2(filter)

        if self.outOfDateFilesXmlBz2(filter).exists():
            return defer.succeed(self._infoForFilesXmlBz2(self.outOfDateFilesXmlBz2(filter)))
        return ret

    def _createFilesXmlBz2(self, filter=None):
        if self._filelistDeferred:
            return self._filelistDeferred
            
        self._filelistDeferred = threads.deferToThread(self._getFilesXmlBz2, filter)
        self._filelistDeferred.addErrback(log.err)
        return self._filelistDeferred
    
    def _getFilesXmlBz2(self, filter=None):
        self.log("_getFilesXmlBz2 %r" % (filter,))
        def _selectAllDirs():
            return list(models.Path.objects.filter(filetype=8).order_by('path'))
        dirs = dbthread.blockingReadCallFromThread(_selectAllDirs)

        if filter is None:
            tmpFilesXmlBz2 = self.config.dataDir.child('tmp-files.xml.bz2')
        else:
            tmpFilesXmlBz2 = self.config.dataDir.child('tmp-files.' + '+'.join(filter) + '.xml.bz2')
            
        out = bz2.BZ2File(tmpFilesXmlBz2.path, 'w')
        def write(data):
            out.write(data.encode('utf-8'))
        write(u'<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n')
        write(u'<FileListing Version="1" Generator="TXConnect %s">\n' % (directconnect.__version__,))

        lastDirParts = []
        for directory in dirs:
            if filter and not directory.passes_filter(filter):
                continue
            currentDirParts = directory.path.split(ntpath.sep)
            commonParts = [part for idx, part in enumerate(lastDirParts) if len(currentDirParts) > idx and lastDirParts[idx] == currentDirParts[idx]]
            toRemove = lastDirParts[len(commonParts):]
            toAdd = currentDirParts[len(commonParts):]
            for part in reversed(toRemove):
                write('</Directory>') # <!-- ' + part + ' -->\n')
            for part in toAdd:
                write(u'<Directory Name=%s>\n' % (quoteattr(part),))
            lastDirParts = currentDirParts
            def _selectFilesInDir(sd):
                return [(ntpath.basename(sf.path), sf.size, sf.tth,) for sf in sd.file_set.exclude(filetype=8)]
            files = dbthread.blockingReadCallFromThread(_selectFilesInDir, directory)
            for name, size, tth in files:
                write(u'<File Name=%s Size="%d" TTH="%s" />\n' % (quoteattr(name), size, tth,))
        for part in reversed(lastDirParts):
            write(u'</Directory>') #<!-- ' + part + ' -->\n')
        write(u'</FileListing>\n')
        out.close()
        tmpFilesXmlBz2.moveTo(self.filesXmlBz2(filter))
        self._filelistDeferred = None
        return self._infoForFilesXmlBz2(self.filesXmlBz2(filter))
    
    @dbthread.readQuery
    def listPath(self, path=''):
        try:
            if path == '':
                paths = models.Path.objects.filter(directory=None)
            else:
                dir = models.Path.objects.get(path=path)
                paths = dir.file_set.all()
            ret = []
            for pp in paths:
                ret.append(dict(name=pp.basename, size=pp.size, tth=pp.tth, filetype=pp.filetype))
            return ret
        except:
            log.err()

class NotInShareRootsError(StandardError):
    pass
    
