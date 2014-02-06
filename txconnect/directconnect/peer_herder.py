import datetime

from twisted.python import log
from twisted.internet import reactor, protocol
from twisted.application import service
from zope.interface import implements

from .. import htb2 as htb

import louie

from . import peer, utils, errors, interfaces

class PeerHerder(service.Service):
    peerTimeout = 60
    peerRetry = 60
    name = 'peerHerder'
    protocol = peer.PeerProtocol

    implements(interfaces.IPeerHerder)

    def __init__(self, locator):
        self.locator = locator
        
        self.rateLimit = self.config['networking'].get('rate_limit', None)

        self.maxSlots = self.config['files'].get('slots', 8)
        
        # order list of who is waiting to download from us
        # list item looks like {peer: Peer(), last_attempt: datetime}
        self._uploadQueue = []
        
        if self.rateLimit:
            self.setupRateLimit()
            self.protocol = htb.ShapedProtocolFactory(self.protocol, self.peerFilter)
        
        self.peerClientFactory = protocol.ClientCreator(reactor, self.protocol, application=self.locator)
        
        self.peerServerFactory = peer.PeerServerFactory(self.locator, self.protocol)
        self.peerServerFactory.listeningPort = reactor.listenTCP(self.config['networking']['port'], self.peerServerFactory)
        self.peerServerFactory.listeningPort.stopListening()
        
        # k: peer, v: callback
        self._peerCheckout = {}
        
        # Peers that we will send a ConnectToMe when the DC fires, k: peer v: IDelayedCall
        self._waitingToConnect = {}
        # Peers we have sent ConnectToMe, k: nick v: dict(hubaddr, connectedTimeoutDelayCall,)
        self._waitingForConnection = {}
        # PeerProtocol instances
        self.connections = []

        # k: peer, v: peer protocol instance
        self.idleDownloadConnections = {}
        
        # k: peer, v: peer protocol instance
        self.downloadConnections = {}
        
        self.usedSlots = 0
        
        self.peerStatus = {}

    def startService(self):
        service.Service.startService(self)
        louie.connect(self.onPeerNew, 'peer:new')
        louie.connect(self.onPeerQuit, 'peer:quit')

        louie.connect(self.onHubUserUpdate, 'hub:user:update')
        louie.connect(self.onHubUserQuit, 'hub:user:quit')
        louie.connect(self.onSearchResultRaw, 'search:result:raw')
        louie.connect(self.onPeerTimeout, 'peer:timeout')
        louie.connect(self.onPeerMaxedOut, 'peer:maxed_out')
    
    def stopService(self):
        service.Service.stopService(self)
        louie.disconnect(self.onPeerNew, 'peer:new')
        louie.disconnect(self.onPeerQuit, 'peer:quit')

        louie.disconnect(self.onHubUserUpdate, 'hub:user:update')
        louie.disconnect(self.onHubUserQuit, 'hub:user:quit')
        louie.disconnect(self.onSearchResultRaw, 'search:result:raw')
        louie.disconnect(self.onPeerTimeout, 'peer:timeout')
        louie.disconnect(self.onPeerMaxedOut, 'peer:maxed_out')

        for peer, waiting in self._waitingForConnection.items():
            waiting['connectedTimeoutDelayCall'].cancel()
        
        for delayedCall in self._waitingToConnect.values():
            if delayedCall.active(): delayedCall.cancel()
        
        for connection in self.connections:
            connection.transport.loseConnection()

    def log(self, msg):
        log.msg(msg, system=self.name)
    
    @property
    def checkedOutPeers(self):
        return self._peerCheckout.keys()
    
    @property
    def activePeers(self):
        peers = []
        for conn in self.connections:
            if conn.peer:
                peers.append(conn.peer)
        for ii in self._waitingForConnection.values():
            peers.append(ii['peer'])
        return peers

    @property
    def waitingPeers(self):
        return self._waitingToConnect.keys()
    
    @property
    def allPeers(self):
        peers = []
        for hub in self.hubHerder.hubs.values():
            for peer, info in hub.peers.items():
                peers.append(peer)
        return peers

    @property
    def botPeers(self):
        bots = []
        for hub in self.hubHerder.hubs.values():
            for peer, info in hub.peers.items():
                if 'client' not in info:
                    bots.append(peer)
        return bots
    
    @property
    def inactivePeers(self):
        return set(self.allPeers) - set(self.activePeers) - set(self.waitingPeers)
    
    @property
    def config(self):
        return interfaces.IConfig(self.locator)

    @property
    def hubHerder(self):
        return interfaces.IHubHerder(self.locator)
        
    def onPeerNew(self, *args, **kwargs):
        self.connections.append(kwargs['sender'])
        
        peer = kwargs['sender'].peer
        if peer in self.peerStatus:
            self.peerStatus[peer].pop('maxed', None)
        
    def onPeerQuit(self, nick, hubId, reason, *args, **kwargs):
        connection = kwargs['sender']
        if connection in self.connections:
            self.connections.remove(connection)
        if not connection.peer:
            return
        peer = connection.peer
        # FIXME: is this right?
        if self.downloadConnections.get(peer, None) == connection:
            del self.downloadConnections[peer]
            louie.send('download:open')
        if peer in self._peerCheckout:
            self.connectionToPeer(peer, delay=self.peerRetry)

    def setupRateLimit(self):
        self.peerFilter = htb.HierarchicalBucketFilter()
        self.peerBucket = htb.Bucket()
        self.peerFilter.buckets[None] = self.peerBucket

        self.peerBucket.maxburst = self.rateLimit
        self.peerBucket.rate = self.rateLimit
    
    """
    update the queue and return where this peer is in it
    """
    def updateUploadQueue(self, peer):
        now = datetime.datetime.now()
        # clean old entries out of the queue
        for ii in self._uploadQueue:
            lastSeen = now - ii['lastAttempt']
            if lastSeen > datetime.timedelta(seconds=300):
                log.msg("removing %r from download queue, last seen %r ago" % (ii['peer'], lastSeen,))
                self._uploadQueue.remove(ii)
                continue
        for idx, ii in enumerate(self._uploadQueue):
            if ii['peer'] != peer:
                continue
            ii['lastAttempt'] = now
            return idx + 1
        self._uploadQueue.append(dict(peer=peer, lastAttempt=now))
        return len(self._uploadQueue)

    def takeASlot(self, peer):
        if self.usedSlots >= self.maxSlots:
            place = self.updateUploadQueue(peer)
            raise errors.MaxedOutError(place)
        elif self._uploadQueue:
            place = self.updateUploadQueue(peer)
            if place > 1:
                raise errors.MaxedOutError(place)
            assert peer == self._uploadQueue[0]['peer']
            self._uploadQueue.pop(0)
        self.usedSlots += 1
        louie.send('client:slots', self, self.unusedSlots, self.maxSlots)
    def releaseASlot(self, peer):
        assert self.usedSlots > 0
        self.usedSlots -= 1
        louie.send('client:slots', self, self.unusedSlots, self.maxSlots)
    @property
    def unusedSlots(self):
        return self.maxSlots - self.usedSlots

    def takeAPeer(self, peer, callback):
        if peer in self._peerCheckout:
            self._peerCheckout[peer].append(callback)
        else:
            self._peerCheckout[peer] = [callback]
            try:
                self.connectionToPeer(peer)
            except RetryError:
                self.connectionToPeer(peer, delay=30)
            except errors.PeerNoLongerConnectedError:
                del self._peerCheckout[peer]
                pass
    def releaseAllPeers(self, callback):
        for peer, callbacks in self._peerCheckout.items():
            if callback in callbacks: 
                self.releaseAPeer(peer, callback)
    def releaseAPeer(self, peer, callback):
        idx = self._peerCheckout[peer].index(callback)
        self._peerCheckout[peer].remove(callback)
        if len(self._peerCheckout[peer]) == 0:
            self._peerCheckout.pop(peer)
        assert not (peer in self.downloadConnections and peer in self._waitingToConnect)
        if peer in self.downloadConnections and idx == 0:
            assert self.downloadConnections[peer].status == 'idle'
            if peer in self._peerCheckout:
                self._peerCheckout[peer][0](self.downloadConnections[peer])
            else:
                louie.send('peer:idle', self, peer)
        elif peer in self._waitingToConnect:
            louie.send('peer:idle', self, peer)
    def whereInLineForPeer(self, peer, callback):
        queue = self._peerCheckout.get(peer, None)
        if not queue:
            return -1
        try:
            return queue.index(callback)
        except ValueError:
            pass
        return -1
            
    def downloadingFromPeer(self, peer):
        return peer in self.downloadConnections and self.downloadConnections[peer].status != 'idle'
    
    def connectionToPeer(self, peer, delay=0):
        """
        @returns: a PeerProtocol instance after the handshake and in
          "Download" mode.  Reuses connections that are already present
        """
        
        if self.downloadingFromPeer(peer):
            return
        if peer in self._waitingToConnect:
            return

        if delay:
            if peer in self._waitingToConnect:
                assert self._waitingToConnect[peer].active()
                callingDelta = datetime.datetime.fromtimestamp(self._waitingToConnect[peer].getTime()) - datetime.datetime.now() 
                self.log('Already connecting to peer in %r' % (callingDelta,))
                return
            self.log('connecting to %r in %r seconds' % (peer, delay,))
            def _reconnect():
                del self._waitingToConnect[peer]
                if peer not in self._peerCheckout:
                    self.log('Not trying to reconnect to %r, because we don\'t need him any more' % (peer,))
                    return
                self.connectionToPeer(peer)
            dc = reactor.callLater(delay, _reconnect)
            self._waitingToConnect[peer] = dc
            return
            
        if peer in self.downloadConnections and self.downloadConnections[peer].status == 'idle':
            if peer in self._peerCheckout:
                callback = self._peerCheckout[peer][0]
                callback(self.downloadConnections[peer])
            else:
                self.log('have connection with %r but no one wants it' % (peer,))
                louie.send('peer:idle', self, peer)
            return
            #return defer.succeed(self.downloadConnections[peer])
            
        try:
            hub = self.hubHerder.hubForPeer(peer)
        except errors.NotConnectedToHubError, ee:
            self.log('Not connected to hub for %r' % (peer,))
            self._peerCheckout.pop(peer, None)
            return

        if peer not in hub.peers:
            #raise errors.PeerNoLongerConnectedError(peer)
            self.log('peer no longer connected, removing from peer checkout: %r' % (peer,))
            self._peerCheckout.pop(peer, None)
            return
        
        #we are already setting up a connection
        if peer.nick in self._waitingForConnection:
            if self._waitingForConnection[peer.nick]["peer"] == peer:
                return #self._waitingForPeer[peer.nick]
            else:
                self.connectionToPeer(peer, delay=30)

        #setup a connection:
        # we have no connections to him that we can use, so lets bring one up
        # - we could send the request and he never answers.  handled
        # - (?) he could connect but use the wrong nick ( maybe, seems like this would be a bug on
        # his end) we don't handle this anyway
        
        if not hub.activeMode:
            raise NotImplementedError("passive mode not done")
        dc = reactor.callLater(self.peerTimeout, self.timeoutPeerConnection, peer)
        #if self._waitingForPeer.has_key(peer):
        #    self._waitingForPeer.append(dd)
        #else:
        #    self._waitingForPeer = [dd]
        self._waitingForConnection[peer.nick] = {
          "connectedTimeoutDelayCall": dc,
          "peer": peer,
        }
        hub.connectToMe(peer)

    def timeoutPeerConnection(self, peer):
        louie.send('peer:timeout', self, peer)
        self.log("timeoutPeerConnection %r" % (peer,))
        del self._waitingForConnection[peer.nick]
        if peer in self._peerCheckout:
            self.log("reconnecting to %r in 30 seconds" % (peer,))
            self.connectionToPeer(peer, delay=30)
        
    def anyDownloadsNeededFromNick(self, nick):
        """
        Used by PeerProtocol to figure out if it should ask for a download connection 
        or not
        """
        return nick in self._waitingForConnection
    
    def registerConnection(self, connection):
        """
        @param connection: a PeerProtocol instance in download mode
        """
        if connection.remoteNick not in self._waitingForConnection:
            self.log("Got a connection from %r in download mode that I don't remember asking for" % (connection.remoteNick,))
            self.log("self._waitingForConnection: %r" % (self._waitingForConnection,))
            return
            
        nfo = self._waitingForConnection[connection.remoteNick]
        del self._waitingForConnection[connection.remoteNick]
        connection.peer = nfo["peer"]
        if nfo.has_key("connectedTimeoutDelayCall") and nfo["connectedTimeoutDelayCall"].active():
            nfo["connectedTimeoutDelayCall"].cancel()
        self.downloadConnections[connection.peer] = connection
        #print "about to callback with a connection: %r" % (connection,)
        #nfo["connectedDefered"].debug = True
        #nfo["connectedDefered"].callback(connection)
        if self._peerCheckout.has_key(connection.peer):
            callback = self._peerCheckout[connection.peer][0]
            callback(connection)
        else:
            self.log('have connection with %r but no one wants it' % (connection.peer,))
            louie.send('peer:idle', self, connection.peer)

    def connectToPeer(self, hub, data):
        myNick, peeraddr = data.split(" ", 1)
        if peeraddr.endswith('S'):
            # this is strongdc asking us to connect securly.  Let's see what happens if we 
            # ignore them
            return 
            #peeraddr = peeraddr[:-1]
        self.log("connecting to %r" % peeraddr)
        peerhost, peerport = utils.parseAddr(peeraddr)
        dd = self.peerClientFactory.connectTCP(peerhost, peerport)
        def _(protocol):
            protocol.hub = hub
            protocol.startHandshake()
            return protocol
        def err(reason):
            self.log("didn't connect because of: ")
            reason.printBriefTraceback()
        dd.addCallbacks(_, err)

    # peerStatus related
    def onHubUserUpdate(self, hubId, peer, info=None, me=False):
        if me:
            return
        if not info.has_key('openSlots'):
            return
        info = dict(openSlots=info['openSlots'], updatedAt=datetime.datetime.now())
            
        current = self.peerStatus.get(peer, {})
        current.update(info)
        
        self.peerStatus[peer] = current

    def onSearchResultRaw(self, *args, **kwargs):
        peer = kwargs['peer']
        info = dict(openSlots=kwargs['slots'][1], updatedAt=datetime.datetime.now())
        
        current = self.peerStatus.get(peer, {})
        current.update(info)
        
        self.peerStatus[peer] = current
        if 'udp_sender' in kwargs:
            if 'udp_sender' in self.peerStatus[peer]:
                if self.peerStatus[peer]['udp_sender'] != kwargs['udp_sender']:
                    self.log('that is odd.  udp sender for %r has changes from %r to %r' % (peer, self.peerStatus[peer]['udp_sender'], kwargs['udp_sender'],))
            self.peerStatus[peer]['udp_sender'] = kwargs['udp_sender']

    def onPeerTimeout(self, peer):
        self.log('timeout for %s' % (peer,))
        info = self.peerStatus.get(peer, {})
        if info.has_key('timeout'):
            info['timeout'] += 1
        else:
            info['timeout'] = 1
        info['updatedAt'] = datetime.datetime.now()
        self.peerStatus[peer] = info
        
    def onPeerMaxedOut(self, peer, data):
        self.log('maxed for %r: data = %r' % (peer, data,))
        info = self.peerStatus.get(peer, {})
        
        try:
            info['maxed'] = int(data)
        except:
            info['maxed'] = -1
        
        info['updatedAt'] = datetime.datetime.now()
        self.peerStatus[peer] = info

    def onHubUserQuit(self, hubId, peer):
        self.peerStatus.pop(peer, None)
        self._uploadQueue = [ii for ii in self._uploadQueue if ii['peer'] != peer]
    
    def isOnline(self, peer):
        try:
            hub = self.hubHerder.hubForPeer(peer)
        except (KeyError, errors.NotConnectedToHubError,):
            return False
        return peer in hub.peers.keys()

    def isBanned(self, peer):
        if self.config.has_key('bans') and unicode(peer) in self.config['bans']:
            return True
        return False

    def peersUniqueOnUdpSender(self, peers):
        peers = peers[:]
        peers.sort(lambda aa, bb: cmp(unicode(aa), unicode(bb)))
        udpSendersSeen = []
        for peer in peers:
            if peer in self.peerStatus and 'udp_sender' in self.peerStatus[peer]:
                if self.peerStatus[peer]['udp_sender'] in udpSendersSeen:
                    peers.remove(peer)
                udpSendersSeen.append(self.peerStatus[peer]['udp_sender'])
        return peers

    #HACK: there has got to be a better way
    def peersUniqueOnNick(self, peers):
        peers = peers[:]
        peers.sort(lambda aa, bb: cmp(unicode(aa), unicode(bb)))
        nicksSeen = []
        for peer in peers:
            if peer.nick in nicksSeen:
                peers.remove(peer)
            nicksSeen.append(peer.nick)
        return peers
            
    def filterAndSort(self, peers):
        peers = [peer for peer in peers if self.isOnline(peer) and not self.isBanned(peer)]
        peers = self.peersUniqueOnUdpSender(peers)
        peers = self.peersUniqueOnNick(peers)

        if not peers:
            return []
            
        def _peercmp(aa, bb):
            if self._peerCheckout.has_key(aa):
                return 1
            if self._peerCheckout.has_key(bb):
                return -1
            aa_info = self.peerStatus.get(aa, {'openSlots': 1})
            bb_info = self.peerStatus.get(bb, {'openSlots': 1})
            
            failed = False
            for nfo in (aa_info, bb_info,):
                if not nfo.has_key('openSlots'):
                    failed = True
                    self.log('ERROR: nfo %r does not have openSlots' % (nfo,))
            if failed:
                return 0
            
            res = cmp(bb_info.get('timeout', 0), aa_info.get('timeout', 0))
            if res != 0:
                return res
            return cmp(aa_info['openSlots'], bb_info['openSlots'])
        
        peers.sort(_peercmp)
        return peers
    
    def peerInfo(self, peer):
        hub = self.hubHerder.hubForPeer(peer)
        return hub.peers[peer]

class RetryError(StandardError):
    pass

class CannotConnectToTwoPeersWithTheSameNick(RetryError):
    pass
