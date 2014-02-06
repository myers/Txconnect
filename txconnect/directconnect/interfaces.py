from zope.interface import Interface, Attribute

class IDownloadQueue(Interface):
    """store a list of Download objects to be downloaded later"""
    
    def download(outfile, tth=None, size=None, type='file', offset=0, priority=10, sources=None):
        """download a file from a peer"""

    def outpaths():
        """all the directories we are downloading files to as a list of strings"""

    def filesForOutpath(outpath):
        """a hash per file that is being downloaded into a directory"""
        
    def getNextForPeer(peer):
        """get the next Download object for a peer"""
        
    def update(download):
        """something has changed about this download, record it"""
        
    def append(newDownload):
        """add a Download object to the queue"""
        
    def remove(download):
        """remove a Download object from the queue"""
        
    def save():
        """save the queue.  for some implementations this is a noop"""

    def removeById(downloadId):
        """remove download by it's id"""
class IHasher(Interface):
    def tthFile(filepath):
        '''return tth root and hash of file'''
    
    def neededBlocks(filepath, root, leaves):
        '''return a list of tuples of (offset, size,)'''

class IDirLister(Interface):
    def listDir(dirpath):
        '''return list of directory entries'''
            
class IMessageMemory(Interface):
    """
    has a .messages property that's a list of event messages
    Use to remember what happened while UI (like the webui) is not 
    connected
    """
    messages = Attribute("list of event messages")
    
class IConfig(Interface):
    """
    Impliment a dict like interface for our config info
    """
    def reload():
        '''reload the configuration file'''
    

class IPeerHerder(Interface):
    def connectionToPeer(peer):
        """returns a defered that results in a connection to `peer` that's in download mode"""

    def releaseASlot():
        """indicates the current connection is done with a download"""
        
class ISearchHerder(Interface):
    def search(term, hubs=None, maxsize=None, minsize=None, filetype=1):
        """
        search peers for a files.  This is more useful for UI driven searches.
        @returns (time, searchFilter) 
          time - number of seconds until this search will be sent out (most hubs limit the frequency of searches)
          searchFilter - instance of SeachFilter. Callers will want to louie.connect to the searchFilter to get results
        """

    def searchWithResults(term, hubs=None, maxsize=None, minsize=None, filetype=1, wait=10):
        """
        search peers for a file, waiting `wait` seconds for results.  This is more useful for code driven searches.
        @returns a Deferred that returns a SearchResults instance
        """
    
    def localSearch(hub, query):
        """search our local share store and return search results"""
    

class IHubHerder(Interface):
    def hubForPeer(hubId):
        """find a hub protocol instances for give peer"""

    def allConnectedHubs():
        """return list of connected hub"""

class IFileSource(Interface):
    size = Attribute("sum of sizes of all the files in this source")
    count = Attribute("count of the files in this source")

    def startIndexer():
        """
        @returns deferred which will be called when the indexing is complete
        """
        
    def search(term, maxsize=None, minsize=None, type=1):
        """
        @returns deferred which will return [(dcPath, size, tth,), ...]
        """

    def getByPath(filepath):
        """
        @param tth base32 tth hash, 24 chars long
        @returns deferred which will return {length: sizeOfFile, fileobj: fileObj, tth: tthOfFile, dcPathName: dcPathName}
        @raises FileNotAvailableError
        """

    def getByTTH(tth):
        """
        @param tth base32 tth hash, 24 chars long
        @returns deferred which will return {length: sizeOfFile, fileobj: fileObj, tth: None, dcPathName: dcPathName}
        @raises FileNotAvailableError
        """

    def getLeavesForTTH(tth):
        """
        @returns deferred which will return {length: sizeOfFile, fileobj: fileObj, tth: None, dcPathName: dcPathName}
        """

    def getFilesXmlBz2(filter=None):
        """
        @returns deferred which will return {length: sizeOfFile, fileobj: fileObj, tth: None, dcPathName: dcPathName}
        """

    def haveFileWithTTH(tth):
        """
        @returns if there is a file with this TTH
        """        

    def listPath(path):
        """
        @param path windows like path name of a directory
        @returns list of files/directories found at that path
        """

class IDownloaderManager(Interface):
    pass

class ITrafficLogger(Interface):
    pass
    
