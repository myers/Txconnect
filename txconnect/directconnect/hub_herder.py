from twisted.python import log
from twisted.internet import reactor, protocol, defer, error
from twisted.application import service
from zope.interface import implements

import louie

from . import hub, utils, interfaces, errors

class HubHerder(service.Service):
    name = 'hubHerder'
    protocol = hub.HubClientProtocol
    retryTimeout = 600

    implements(interfaces.IHubHerder)

    def __init__(self, application):
        self.application = application

        self.hubClientFactory = protocol.ClientCreator(reactor, self.protocol, application=self.application)
        
        # key: hubId, v: hubprotocol instance
        self.hubs = {}

        # key: hubId, v: current status
        self.activeHubs = {}
        louie.connect(self.onHubStatus, 'hub:status')
        louie.connect(self.onHubQuit, 'hub:quit')

    @property
    def fileSource(self):
        return interfaces.IFileSource(self.application)

    def log(self, msg):
        log.msg(msg, system=self.name)
        
    def startService(self):
        service.Service.startService(self)
        self.fileSource.setupDone.addCallbacks(self.connectToAllHubs, log.err)
        
    def stopService(self):
        service.Service.stopService(self)
        for hub in self.hubs.values():
            hub.transport.loseConnection()
        
    def connectToAllHubs(self, res=None):
        self.log('connecting to hubs')
        for hubcred in self.config['hubs']:
            if not hubcred['active']:
                continue
            hubId = hubcred['hostname']
            louie.send('hub:new', hubId, {})
            dd = self.connectToHub(hubId)
            dd.addCallbacks(
                callback=self.wait, 
                callbackArgs=(hubId,),
                errback=self.retryConnect, 
                errbackArgs=(hubId,))

    def hubForPeer(self, peer):
        try:
            return self.hubs[str(peer.hubId)]
        except KeyError:
            #self.log('could not find %r in %r' % (str(peer.hubId), self.hubs.keys(),))
            raise errors.NotConnectedToHubError("%r" % (peer.hubId,))

    def allConnectedHubs(self):
        return self.hubs.values()
                
    def onHubStatus(self, hubId, status):
        self.log('onHubStatus %r %s' % (hubId, status,))
        self.activeHubs[hubId] = status
        
    @property
    def config(self):
        return interfaces.IConfig(self.application)

    
    def wait(self, res, hubId):
        louie.send('hub:status', self, hubId, 'logged in')

    def hubCred(self, hubprotocol):
        for cred in self.config['hubs']:
            if cred['hostname'] == hubprotocol.hubId:
                return cred
        raise Exception, 'could not find cred for %r' % (hubprotocol.hubAddr,)

    def connectToHub(self, hubId, activeMode=True):
        hubAddr = utils.parseAddr(hubId)
        louie.send('hub:status', self, hubId, 'resolving %r' % (hubAddr[0],))
        dd = reactor.resolve(hubAddr[0])
        return dd.addCallback(self._connectToHub, hubAddr[1], hubId, activeMode)

    def _connectToHub(self, hubIp, hubPort, hubId, activeMode):
        louie.send('hub:status', self, hubId, 'connecting to %s:%s' % (hubIp, hubPort,))
        dd = self.hubClientFactory.connectTCP(hubIp, hubPort)
        def _(protocol):
            protocol.hubId = hubId
            protocol.hubAddr = (hubIp, hubPort)
            protocol.activeMode = activeMode
            self.hubs[hubId] = protocol
            protocol.cred = self.hubCred(protocol)
            protocol.loggedInDeferred = defer.Deferred()
            return protocol.loggedInDeferred
        return dd.addCallback(_)

    def retryConnect(self, res, hubId):
        log.err(res)
        louie.send('hub:status', self, hubId, 'disconnected: %r' % (res.value.args,))
        louie.send('hub:status', self, hubId, 'retrying in %s secs' % (self.retryTimeout,))
        dd = defer.Deferred()
        def _reconnect():
            d2 = self.connectToHub(hubId)
            d2.addCallbacks(
                callback=dd.callback, 
                callbackArgs=(hubId,),
                errback=self.retryConnect, 
                errbackArgs=(hubId,))
        reactor.callLater(self.retryTimeout, _reconnect)
        return dd

    def onHubQuit(self, hubId, reason, sender=None):
        louie.send('hub:status', self, hubId, 'disconnected')
        if self.hubs.has_key(hubId):
            del self.hubs[hubId]
        else:
            self.log('could not find hub in list of connected hubs: %r' % (hubId,))
        if reason.type == error.ConnectionDone:
            return
        if self.running:
            self.retryConnect(reason, hubId)
