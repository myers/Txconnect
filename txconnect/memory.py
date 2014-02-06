import pickle, datetime
from twisted.application import service

from zope.interface import implements
import louie

from directconnect.interfaces import IMessageMemory, IConfig

class MemoryService(service.Service):
    name = 'memory'
    implements(IMessageMemory)
    
    def __init__(self, locator):
        self.locator = locator
        self.messages = []
        louie.connect(self.onEvent, 'hub:status')
        louie.connect(self.onEvent, 'hub:global_to')
        louie.connect(self.onEvent, 'hub:to')
        louie.connect(self.onEvent, 'hub:sent_to')
        louie.connect(self.onEvent, 'hub:chat')

    @property
    def config(self):
        return IConfig(self.locator)
        
    def onEvent(self, *args, **kwargs):
        msg = [kwargs['signal']] + list(args)
        self.messages.append(msg)

    def stopService(self):
        self.config.dataDir.child('m').makedirs()
        pickle.dump(self.messages, self.config.dataDir.child('m').child('memory.' + datetime.datetime.now().isoformat() + '.pickle').open('wb'))
        return service.Service.stopService(self)
