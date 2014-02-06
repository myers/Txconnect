import copy

class Download(object):
    size = None
    offset = 0
    tth = None
    outfilepath = None
    outFile = None
    
    def __init__(self, outfile, peerPathnames, tth=None, size=None, offset=0, type='file', priority=0, label=None):
        if isinstance(outfile, basestring):
            if isinstance(outfile, unicode):
                outfile = outfile.encode('utf-8')
            self.outfilepath = outfile
            self.outFile = None
        elif hasattr(outfile, "write"):
            self.outfilepath = None
            self.outFile = outfile
        else:
            raise ValueError("got %r for outfile" % (outfile,))
        self.tth = tth
        self.size = size
        self.offset = offset
        self.type = type
        self.priority = priority
        self.label = label
        # k: peer v: pathname of file on peer
        self.peerPathnames = peerPathnames
        self.startTransfer = None
        self.leaves = None
        self.tthVerifier = None
        self._id = None
        self.stupidPeerMode = False

    @property
    def peers(self):
        return self.peerPathnames.keys()
        
    def setOutfilepath(self, path):
        # I don't know why we were being so protective over this
        #if hasattr(self, '_outfilepath') and self._outfilepath != path:
        #    import traceback
        #    traceback.print_stack()
        #    raise Exception('cannot change %r to %r' % (self._outfilepath, path,))
        self._outfilepath = path
    def getOutfilepath(self):
        return self._outfilepath
    outfilepath = property(getOutfilepath, setOutfilepath)
         
    def setId(self, id):
        if self._id is not None:
            raise Exception('cannot change id from %r to %r' % (self._id, id,))
        self._id = id
    def getId(self):
        return self._id
    id = property(getId, setId)
    
    def canMultisource(self):
        return self.tth and self.size and not self.stupidPeerMode

    def __repr__(self):
        return "<%s %s %s at %x>" % (self.__class__.__name__, self.id, self.outfilepath, id(self),)

    def __getstate__(self):
        dd = copy.copy(self.__dict__)
        dd["outFile"] = None
        dd["startTransfer"] = None
        dd["tthVerifier"] = None
        return dd

