import os, time, tempfile, shutil, cPickle as pickle, copy, pprint, datetime

from twisted.python import log
from twisted.internet import reactor, defer, error, threads
from twisted.application import service

from zope.interface import implements

import louie

from . import filelist, errors, interfaces
from ..tth import TTH

class DuplicateFileError(StandardError):
    pass

class PickleDownloadQueue:
    implements(interfaces.IDownloadQueue)

    def __init__(self):
        self.saving = False
        self.downloads = []
        if os.path.isfile("downloads.pickle"):
            self.downloads = pickle.load(file("downloads.pickle", "rb"))

    def getNextForPeer(self, peer):
        for download in self.downloads:
            if download.peerPathnames.has_key(peer):
                return defer.succeed(download)
        return defer.succeed(None)
        
    def append(self, newDownload):
        for dl in self.downloads:
            if dl.outfilepath == newDownload.outfilepath:
                raise DuplicateFileError("%r" % (newDownload.outfilepath,))
            #FIXME don't know what I was doing here
            #for peer in newDownload.peerPathnames.keys():
            #    if dl.peerPathnames.has_key(peer) and newDownload.outfilepathfilepath == dl.peerPathnames[peer]:
            #        raise DuplicateFileError("%r" % (outfile,))
        #download = Download(outfile, {peer: filepath}, tth, size, offset)
        self.downloads.append(newDownload)
        return defer.succeed(newDownload)

    def remove(self, download, error=False):
        self.downloads.remove(download)
                
    def save(self):
        if self.saving:
            return 
        self.saving = True
        
        def real_save():
            pickle.dump(self.downloads, file("downloads.pickle.temp", "wb"), 2)
            os.rename("downloads.pickle.temp", "downloads.pickle")
        def after_save(res):
            self.saving = False
        dd = threads.deferToThread(real_save)
        dd.addCallback(after_save, log.err)
        return dd        

    def update(self, download):
        pass
        