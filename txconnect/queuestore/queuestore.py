import os, datetime, weakref

from twisted.python import log
from twisted.python.filepath import FilePath

import louie

from ..directconnect import download
from ..directconnect.peer import Peer

from ..directconnect.interfaces import IDownloadQueue, IConfig
from zope.interface import implements

from .. import dbthread
from . import models
from ..sharestore import models as sharestore_models

class QueueStore:
    implements(IDownloadQueue)
    
    def __init__(self, locator):
        self._downloads = weakref.WeakValueDictionary()
        self.locator = locator

    @property
    def config(self):
        return IConfig(self.locator)

    def log(self, msg):
        log.msg(msg, system="QueueStore")
        
    def download(self, outfile, tth=None, size=None, offset=0, type='file', priority=0, sources=None, label=None):
        self.log('download %r' % ((outfile, tth, size, offset, type, priority, sources,),))
        if sources is None:
            sources = {}
        for peer, filepath in sources.items():
            if filepath.count("/"):
                raise Exception("trying to download file with '/' in name: %r" % (filepath,))
        if isinstance(outfile, basestring):
            outfile = os.path.join(self.config['files']['finished'], outfile)
        dl = download.Download(outfile, sources, tth=tth, size=size, offset=offset, type=type, priority=priority, label=label)
        dd = self.append(dl)
        def _afterQueued(res):
            if not dl.id:
                self.log('download NOT queued %r' % (outfile,))
                return
            if res:
                self.log("download queued: %r %r" % (outfile, type,))
                louie.send('download:queued', self, dl)
            return res
        return dd.addCallbacks(_afterQueued, log.err)

    def _filter(self, qs):
        # hack to limit downloads
        return qs.filter(priority__gte=7)
        
    @dbthread.readQuery
    def outpaths(self):
        ret = {}
        for dirname in [v['directory'] for v in models.File.objects.all().values('directory').distinct()]:
            current = ret
            nextPartRoot = False
            for part in dirname.split(os.sep):
                if part == '':
                    nextPartRoot = True
                    continue
                elif nextPartRoot:
                    nextPartRoot = False
                    part = os.sep + part
                if part not in current.keys():
                    current[part] = {}
                current = current[part]
        return ret    

    @dbthread.readQuery
    def filesForOutpath(self, outpath):
        ret = []
        for ff in models.File.objects.filter(directory=outpath):
            ret.append(dict(
              filename=ff.name, 
              tth=ff.tth, 
              size=ff.size, 
              sources=ff.source_set.count()
            ))
        return ret    
        
    def _fileToDownload(self, fileModel):
        ret = self._downloads.get(fileModel.id, None)
        if not ret:
            peerPathnames = {}
            for source in fileModel.source_set.all():
                peerPathnames[Peer(source.peer)] = source.dcPath
            ret = download.Download(
              fileModel.outpath, 
              peerPathnames, 
              tth=fileModel.tth, 
              size=fileModel.size, 
              type=fileModel.type, 
              priority=fileModel.priority,
              label=fileModel.label
            )
            ret.id = fileModel.id
            ret.fileModel = fileModel
            self._downloads[fileModel.id] = ret
        return ret
    
    @dbthread.readQuery
    def downloadWithOldestSources(self):
        try:
            ff = models.File.objects.all().include(type='file').exclude(tth=None).order_by('last_searched_for_sources')[0]
            dl = self._fileToDownload(ff)
            dl.last_searched_for_sources = ff.last_searched_for_sources
            return dl
        except IndexError:
            return None

    def update(self, download):
        return self.append(download)

    @dbthread.writeQuery
    def deleteAllWithLabel(self, label):
        label = models.Label.objects.get(label=label)
        label.file_set.all().delete()
        
    def append(self, newDownload):
        self.log('append: %r' % (newDownload,))
        dd = self._append(newDownload)
        def _error(error):
            print newDownload
            print error
        dd.addErrback(_error)
        return dd

    @dbthread.writeQuery
    def _append(self, newDownload):
        if newDownload.label:
            label, created = models.Label.objects.get_or_create(label=newDownload.label)
        else:
            label = None
 
        # used for debugging.  we can see what's different.
        try:
            ff = models.File.objects.get(
              directory=os.path.dirname(newDownload.outfilepath), 
              name=os.path.basename(newDownload.outfilepath))
            assert ff.tth == newDownload.tth
            assert ff.size == newDownload.size
            assert ff.type == newDownload.type, "%r %r" % (ff.type, newDownload.type,)
        except models.File.DoesNotExist:
            pass
        
        ff, created = models.File.objects.get_or_create(
          directory=os.path.dirname(newDownload.outfilepath),
          name=os.path.basename(newDownload.outfilepath),
          tth=newDownload.tth,
          size=newDownload.size,
          type=newDownload.type,
          defaults=dict(leaves=newDownload.leaves, priority=newDownload.priority, label=label)
        )
        # this might be
        # a) a completely new download
        # b) a download we are saving again
        # c) a new request to download a file we already had in the queue
        if created:
            assert newDownload.id == None, newDownload.id
            newDownload.id = ff.id
        else:
            assert newDownload.id is None or newDownload.id == ff.id
            if not newDownload.id:
                newDownload.id = ff.id
        ff.leaves = newDownload.leaves
        ff.last_searched_for_sources = datetime.datetime.now()
        ff.save()
        for peer, path in newDownload.peerPathnames.items():
            source, created = models.Source.objects.get_or_create(
              peer=unicode(peer),
              dcPath=path,
              file=ff
            )
        toDelete = ff.source_set.exclude(peer__in=[unicode(peer) for peer in newDownload.peerPathnames.keys()])
        toDelete.delete()
        assert ff.source_set.count() == len(newDownload.peerPathnames), "didn't have the same number of sources %d vs %d" % (ff.source_set.count(), len(newDownload.peerPathnames),)
        return created
        
    @dbthread.writeQuery
    def remove(self, download, **kwargs):
        self.log('removing %r' % (download,))
        ff = models.File.objects.get(pk=download.id)
        ff.delete()
        
    def save(self):
        pass

    @dbthread.readQuery
    def findDownloadFromTTHs(self, tths):
        try:
            ff = models.File.objects.filter(tth__in=tths).order_by('-priority', 'last_searched_for_sources')[0]
        except IndexError:
            return None
        return self._fileToDownload(ff)

    @dbthread.readQuery
    def tthOfAllDownloads(self):
        return [str(row['tth']) for row in models.File.objects.values('tth')]

    @dbthread.readQuery
    def getNextForPeer(self, peer, test=None):
        sources = models.Source.objects.filter(peer=unicode(peer))
        files = models.File.objects.filter(source__in=sources).order_by('-priority')
        for ff in files:
            if (test and test(ff.id)) or (test is None):
                return self._fileToDownload(ff)
        return None

    """
    I tried passing in a list of ids into the database to exclude but that didn't work 
    -- but now I think that was because of a race condition
    """
    @dbthread.readQuery
    def findBestDownloadOtherThanThese(self, test, peers):
        pc = None
        for ff in self._filter(self._bestPartiallyCompleteFiles()):
            if test(ff.id):
                pc = ff
                break

        # HACK
        if pc:
            self.log('download id %r is from pc' % (pc.id,))
            return self._fileToDownload(pc)

        online = None
        for ff in self._filter(self._downloadFromPeers(peers)):
            if test(ff.id):
                online = ff
                break

        #HACK
        if online:
            self.log('download id %r is from online' % (online.id,))
            return self._fileToDownload(online)
                
        normal = None
        one_hour_ago = datetime.datetime.now() - datetime.timedelta(hours=1)
        for ff in self._filter(models.File.objects.filter(last_searched_for_sources__lt=one_hour_ago, tth__isnull=False).order_by('-priority', 'last_searched_for_sources')):
            if test(ff.id):
                normal = ff
                break
          
        if getattr(pc, 'priority', -1) > getattr(normal, 'priority', -1):
            return self._fileToDownload(pc)
        if normal:
            self.log('download id %r is from normal' % (normal.id,))
            return self._fileToDownload(normal)            
        return None

    def _downloadFromPeers(self, peers, notIn=None):
        peers = [unicode(peer) for peer in peers]
        qs = models.File.objects.filter(source__peer__in=peers).order_by('-priority', 'last_searched_for_sources')
        if notIn:
            qs = qs.exclude(id__in=notIn)
        return qs
    
    
    def _bestPartiallyCompleteFiles(self, notIn=None):
        tths = self.partiallyCompleteDownloadTTHs()
        qs = models.File.objects.filter(tth__in=tths).order_by('-priority', 'last_searched_for_sources')
        if notIn:
            qs = qs.exclude(id__in=notIn)
        return qs
        
    def partiallyCompleteFiles(self):
        incoming = FilePath(self.config['files']['incoming'])
        return [fp for fp in incoming.globChildren('*.txconnect') if fp.getsize() > 0]
    
    def partiallyCompleteDownloadTTHs(self):
        return [self.tthFromPartiallyCompleteFilepath(fp) for fp in self.partiallyCompleteFiles()]

    def tthFromPartiallyCompleteFilepath(self, fp):
        return fp.basename().replace('.txconnect', '')

    @dbthread.readQuery
    def cleanIncomingFiles(self):
        try:
            tths = self.tthOfAllDownloads()
            for fp in self.partiallyCompleteFiles()[:100]:
                tth = self.tthFromPartiallyCompleteFilepath(fp)
                if tth not in tths:
                    if sharestore_models.Path.objects.filter(tth=tth):
                        self.log('delete %r which was an old temp download i guess' % (fp,))
                    else:
                        self.log('delete %r WTF? maybe a delete download?' % (fp,))
                    fp.remove()
        except Exception, ee:
            print ee

    @dbthread.readQuery
    def getById(self, id):
        return self._fileToDownload(models.File.objects.select_related().get(pk=id))

    @dbthread.writeQuery
    def removeById(self, id):
        models.File.objects.get(pk=id).delete()
