from twisted.python import log

from .directconnect import interfaces

class ServiceUtil(object):
    def log(self, msg):
        log.msg(msg, system=self.name)
            
    @property
    def queue(self):
        return interfaces.IDownloadQueue(self.locator)
        
    @property
    def config(self):
        return interfaces.IConfig(self.locator)

    @property
    def peerHerder(self):
        return interfaces.IPeerHerder(self.locator)

    @property
    def hubHerder(self):
        return interfaces.IHubHerder(self.locator)

    @property
    def searchHerder(self):
        return interfaces.ISearchHerder(self.locator)
