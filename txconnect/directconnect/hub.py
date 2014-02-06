import datetime, re, time, zlib

from twisted.python import log
from twisted.protocols import basic
from twisted.internet import reactor, defer

import louie

from ..directconnect import __version__, DC_ENCODING

from . import search, utils, errors, interfaces
from .peer import Peer
from ..priority_queue import PriorityQueue

# TODO: PeerList class
class HubClientProtocol(basic.LineReceiver):
    """
    I talk to Direct Connect Hubs.  One per tcp connection to a hub.
    """
    pauseBetweenSearches = 20

    delimiter = "|"
    
    def __init__(self, application):
        self.application = application
        
        self.hubId = None
        self.hubAddr = None
        self.hubname = None
        self.peers = {}
        self.supports = []
        self.cred = None
        self.activeMode = True # FIXME: support passive mode
        self.pendingSearches = PriorityQueue()
        self.searchTimer = None
        self.ready = False
        self.hubConnected = False
        self.extendedProtocol = False
        self.userCommands = []
        self.lastSentMyINFO = None
        self.lastSearchArgs = None
        self.periodiclySendMyINFOId = None

        louie.connect(self.onShareStoreSize, 'share_store:size')

    @property
    def filter(self):
        return self.cred.get('share_filter', None)
        
    def log(self, msg):
        return log.msg(msg, system="Hub:%s" % (self.hubId,))
        
    @property
    def nick(self):
        return self.cred['nick']

    @property
    def config(self):
        return interfaces.IConfig(self.application)

    @property
    def fileSource(self):
        return interfaces.IFileSource(self.application)

    @property
    def peerHerder(self):
        return interfaces.IPeerHerder(self.application)

    @property
    def searchHerder(self):
        return interfaces.ISearchHerder(self.application)

    @property
    def id(self):
        #if self.hubAddr is None:
        #    raise Exception, "can't have an id yet"
        #return '%s:%d' % self.hubAddr
        return self.hubId

    def connectionLost(self, reason):
        self.log('lost connection: %r' % (reason,))
        if self.searchTimer:
            self.searchTimer.cancel()
        if self.periodiclySendMyINFOId:
            self.periodiclySendMyINFOId.cancel()
        louie.send('hub:quit', self, self.id, reason)
            
    def onShareStoreSize(self, *args, **kwargs):
        self.sendMyINFO()
    
    def peerForNick(self, nick):
        assert isinstance(nick, unicode)
        for peer, info in self.peers.items():
            assert isinstance(peer.nick, unicode)
            if peer.nick == nick:
                return peer
        raise errors.PeerNotFound(nick)
          
    def connectionMade(self):
        basic.LineReceiver.connectionMade(self)

    def sendLine(self, line):
        if type(line) is unicode:
            line = line.encode(DC_ENCODING)
        self.log(">>> %r" % (line,))
        return basic.LineReceiver.sendLine(self, line)

    def lineReceived(self, line):
        if not line.startswith("$Quit"):
            self.log("<<< %r" % (line,))
        cmd, data = utils.parseCommand(line)
        if cmd is None:
            return
        phandler = getattr(self, "handle%s" % (cmd,), None)
        if phandler:
            try:
                data = phandler(data)
            except UnicodeDecodeError, ee:
                log.err('Error while decoding %r' % (line,))
                log.err(ee)
        else:
            self.log("no handler for %r: %r" % (cmd, data,))

    def handleLock(self, lock):
        if 'VIPERHUB' in lock or 'py-dchub' in lock or 'YnHub' in lock or 'FLEXHUB' in lock:
            self.extendedProtocol = False
        elif lock.startswith('EXTENDEDPROTOCOL'):
            self.extendedProtocol = True

        if self.extendedProtocol:
            self.sendLine("$Supports UserCommand NoGetINFO NoHello QuickList ZPipe")
        else:
            self.sendLine("$Key %s" % (utils.lockToKey(lock),))
            self.sendLine("$ValidateNick %s" % (self.nick,))

    def say(self, msg):
        self.sendLine("<%s> %s" % (self.nick, msg,))

    def sendMessage(self, peer, msg):
        self.sendLine("$To: %s From: %s $<%s> %s" % (peer.nick.encode(DC_ENCODING), self.nick, self.nick, msg.encode(DC_ENCODING),))
        louie.send('hub:sent_to', self, peer, datetime.datetime.utcnow().isoformat(), msg, Peer(self.nick, self.hubId))

    def search(self, term, maxsize=None, minsize=None, searchType=1, priority=0):
        # hubs aren't happy if you keep repeating the same query
        args = (term, maxsize, minsize, searchType,)
        assert self.lastSearchArgs != args, "%r" % (args,)
        self.lastSearchArgs = args

        if not self.ready:
            raise Exception('hub %r not ready to search for %r' % (self.id, term,))
        term = term.encode(DC_ENCODING, 'replace')
        if term == 'None':
            raise ValueError('term was %r' % (term,))
        if maxsize and minsize:
            raise ValueError("DC protocol cannot search with a maxsize and minsize")
            
        term = term.replace(" ", "$")
        if maxsize:
            query = "T?T?%d?%d?%s" % (maxsize, searchType, term,)
        elif minsize:
            query = "T?F?%d?%d?%s" % (minsize, searchType, term,)
        else:
            query = "F?T?0?%d?%s" % (searchType, term,)
        if self.activeMode:
            cmd = "$Search %s:%s %s" % (self.searchHerder.ip, self.searchHerder.port, query,)
        else:
            cmd = "$Search Hub:%s %s" % (self.nick, query,)
        
        class SearchTask(object):
            def __init__(self, cmd):
                self.cmd = cmd
                self.deferred = None
            def __repr__(self):
                return '<%s for %r at 0x%x>' % (self.__class__, self.cmd, id(self),)
        
        searchTask = SearchTask(cmd)
        def _cancelSearch(deferred):
            self.log("removing search from queue: %r" % (searchTask,))
            try:
                self.pendingSearches.deleteTask(searchTask)
                self.log("removed search from queue: %r" % (searchTask,))
            except KeyError, ee:
                self.log("failed to remove search from queue: %r because of %r" % (searchTask, ee))

        if self.searchTimer and self.searchTimer.active():
            searchTask.deferred = defer.Deferred(canceller=_cancelSearch)
            howManyInFront = self.pendingSearches.addTask(priority, searchTask)

            timeTilSearch = self.searchTimer.getTime() - time.time() + (self.pauseBetweenSearches * howManyInFront)
            self.log('computing search time: %r %r %r %r = %r' % (self.searchTimer.getTime(), time.time(), self.pauseBetweenSearches, len(self.pendingSearches), timeTilSearch,))
            assert timeTilSearch > -0.5
            if timeTilSearch < 0: 
                timeTilSearch = 0

            return timeTilSearch, searchTask.deferred
        #FIXME: the limit on how frequent you can do a search on a hub is set on a per 
        # hub basis, with no standard way to communicate the limit.  10 seconds is the 
        # upper bound on what I've seen in the wild.
        self.searchTimer = reactor.callLater(self.pauseBetweenSearches, self.onSearchTimer)
        self.sendLine(cmd)
        return 0, defer.succeed(True)
                
    def onSearchTimer(self):
        searchTask = self.pendingSearches.getTopPriority()
        if not searchTask:
            self.searchTimer = None
            return
        self.searchTimer = reactor.callLater(self.pauseBetweenSearches, self.onSearchTimer)
        
        self.sendLine(searchTask.cmd)
        searchTask.deferred.callback(True)
    
    def connectToMe(self, peer):
        self.peerHerder.peerServerFactory.expectPeer(peer)
        self.sendLine("$ConnectToMe %s %s:%s" % (peer.nick.encode(DC_ENCODING), self.config['networking']['external_ip'], self.config['networking']['port'],))
 
    def handleSearch(self, data):
        """
        Handle search request from other peers passed on to us by the 
        hub
        
        TODO: the key "peer" is confusing
        """
        # 192.168.42.5:4242 F?T?0?1?terminology.txt
        query = dict(hub=self, minsize=None, maxsize=None)
        query['peer'], data = data.split(' ', 1)
        # TODO: handle passive peers
        limit, minOrMax, size, query['filetype'], query['term'] = data.split('?', 4)
        query['term'] = query['term'].decode(DC_ENCODING).replace('$', ' ')
        if limit == 'T' and minOrMax == 'T':
            query['maxsize'] = int(size)
        elif limit == 'T' and minOrMax == 'F':
            query['minsize'] = int(size)
        query['filetype'] = int(query['filetype'])

        self.searchHerder.localSearch(self, query)
    
    def handleQuit(self, nick):
        try:
            peer = self.peerForNick(nick.decode(DC_ENCODING))
            del self.peers[peer]
            self.log('peer quit: %r' % (peer,))
            louie.send('hub:user:quit', self, self.id, peer)
        except errors.PeerNotFound:
            pass
    
    def handleHubName(self, hubname):
        hubname = hubname.decode(DC_ENCODING)
        self.ready = True
        louie.send('hub:name', self, self.id, hubname)
        self.hubname = hubname
        
        if self.extendedProtocol and not self.hubConnected:
            louie.send('hub:connected', self, self.id, self.hubname)
            self.hubConnected = True

    def handleGetPass(self, line):
        self.sendLine("$MyPass %s" % (self.cred["password"],))
    
    """
    Used in passive mode(?)
    """
    def handleSR(self, line):
        res = search.parseSearchResults(line)
        res["peer"] = Peer(res["nick"], self.id)
        louie.send('search:result:raw', self, **res)
            
    def handleSupports(self, supports):
        self.supports = supports.split()
        if self.extendedProtocol:
            self.sendMyINFO()
            self.sendLine('$GetNickList')

    def handleRevConnectToMe(self, line):
        remotenick, mynick = line.split()
        assert mynick == self.cred['nick']
        peer = Peer(remotenick, self.id)
        self.connectToMe(peer)
        
    def handleHello(self, nick):
        if nick == self.nick:
            self.sendLine("$Version 1,0091")
            self.sendLine("$GetNickList")
            self.sendMyINFO()
            louie.send('hub:connected', self, self.id, self.hubname)
            self.hubConnected = True
        
        peer = Peer(nick, self.id)
        self.peers[peer] = dict(op=False, connected=datetime.datetime.now())
        louie.send('hub:user:new', self, self.id, peer, info=self.peers[peer], me=True)

    def sendMyINFO(self):
        if not self.cred:
            return
        if self.lastSentMyINFO is not None and (datetime.datetime.now() - self.lastSentMyINFO) < datetime.timedelta(seconds=300):
            return
            
        nfo = dict(shareSize=self.fileSource.size, client_name='txconnect', client_version=__version__)
        nfo.update(**self.cred)
            
        nfo["description"] = "<%(client_name)s V:%(client_version)s,M:A,H:0/1/0,S:10>" % nfo
        # '$MyINFO $ALL czdc <++ V:0.699,M:A,H:1/0/0,S:6,L:15>$ $LAN(T1)\x01$iamferret@yahoo.com$0$'
        self.sendLine("$MyINFO $ALL %(nick)s %(description)s$ $%(connection)s\x01$%(email)s$%(shareSize)s$" % nfo)
        self.lastSentMyINFO = datetime.datetime.now()
        if self.periodiclySendMyINFOId and self.periodiclySendMyINFOId.active():
            self.periodiclySendMyINFOId.delay(1200)
        else:
            self.periodiclySendMyINFOId = reactor.callLater(1200, self.sendMyINFO)

    def handleMyINFO(self, line):
        _all, nick, info = line.split(" ", 2)
        peer = Peer(nick, self.id)
        me = False
        if nick == self.nick:
            me = True
        if not self.peers.has_key(peer):
            self.peers[peer] = dict(op=False, connected=datetime.datetime.now())
            louie.send('hub:user:new', self, self.id, peer, info=self.peers[peer], me=me)
        self.peers[peer]['infoRaw'] = info.decode(DC_ENCODING)
        try:
            self.peers[peer].update(parseMyINFO(self.peers[peer]['infoRaw']))
        except MyInfoParseError:
            self.log('could not parse %r' % (self.peers[peer]['infoRaw'],))
        self.peers[peer]['infoUpdatedAt'] = datetime.datetime.now()
        louie.send('hub:user:update', self, self.id, peer, info=self.peers[peer], me=me)

    def handleChat(self, line):
        louie.send('hub:chat', self, self.id, datetime.datetime.utcnow().isoformat(), line.decode(DC_ENCODING))
    
    def handleTo(self, line):
        # e.g. line = '$To: \xa5iamferret From: iamferret $<iamferret> hello'
        # '$To: test From: Hub $Welcome to the hub. Enjoy your stay.'
        to_match = re.match(r'(?P<to>[^ ]+)\s*From:\s*(?P<from>[^ ]+)\s*\$(?P<msg>.*)', line, re.MULTILINE|re.DOTALL)
        if not to_match:
            raise errors.ParseError("Couldn't handle this message %r" % (line,))
        peer = Peer(to_match.group('from'), self.id)

        mm = re.match(r'<(?P<from2>[^>]+)>\s*(?P<msg>.*)', line, re.MULTILINE|re.DOTALL)
        if mm and to_match.group('from') != mm.group('from2'):
            real_peer = Peer(mm.group('from2'), self.id)
            room = to_match.group('from')
            room_peer = peer
            msg = mm.group('msg')
            louie.send('hub:chat_room', self, room_peer, real_peer, datetime.datetime.utcnow().isoformat(), msg.decode(DC_ENCODING))
        else:
            msg = to_match.group('msg')
            louie.send('hub:to', self, peer, datetime.datetime.utcnow().isoformat(), msg.decode(DC_ENCODING))

    def handleNickList(self, data):
        self.ready = True
        # trim off the last $$
        nicks = data[:-2].split("$$")
        self.peers = {}
        for nick in nicks:
            peer = Peer(nick, self.id)
            me = (nick == self.nick)
            self.peers[peer] = dict(op=False, connected=datetime.datetime.now())
            louie.send('hub:user:new', self, self.id, peer, info=self.peers[peer], me=me)
            if 'NoGetINFO' not in self.supports and not me:
                self.sendLine('$GetINFO %s %s' % (nick, self.nick,))

    def handleOpList(self, data):
        # trim off the last $$
        nicks = data[:-2].split("$$")
        for nick in nicks:
            if nick == '':
                continue
            peer = Peer(nick, self.id)
            if not self.peers.has_key(peer):
                self.peers[peer] = dict(op=True, connected=datetime.datetime.now())
                me = (nick == self.nick)
                louie.send('hub:user:new', self, self.id, peer, info=self.peers[peer], me=me)
                if 'NoGetINFO' not in self.supports:
                    self.sendLine('$GetINFO %s %s' % (nick, self.nick,))
            else:
                self.peers[peer]["op"] = True

    def handleGlobalTo(self, data):
        nick, message = data.decode(DC_ENCODING).split('>', 1)
        nick = nick[1:]
        louie.send('hub:global_to', self, self.id, nick, datetime.datetime.utcnow().isoformat(), message)

    def handleZOn(self, data):
        self.setRawMode()
        self.buffer = []
        self.decompressor = zlib.decompressobj()
    
    def rawDataReceived(self, data):
        self.buffer.append(self.decompressor.decompress(data))
        if self.decompressor.unused_data:
            self.buffer.append(self.decompressor.unused_data)
            self.setLineMode(''.join(self.buffer))

    def handleUserCommand(self, data):
        self.userCommands.append(data)
    
    def handleConnectToMe(self, data):
        self.peerHerder.connectToPeer(self, data)

class MyInfoParseError(StandardError):
    pass
    
def parseMyINFO(myINFO):
    ret = dict()
    
    if myINFO.count('$') != 5:
        raise MyInfoParseError('not enough $')
    try:
        desc, _blank, ret['connectionType'],  ret['email'], ret['shareSize'], _blank = myINFO.split('$', 5)
        
        ret['connectionType'] = ret['connectionType'][:-1]
        
        if desc.count('<') and desc.count('>'):
            ret['comment'], desc = desc.split('<', 1)
            desc = desc[:-1]
            if desc.count(',') < 3:
                raise MyInfoParseError('not enough commas')
            client, active, hubs, slots = desc.split(',', 3)
        
            ret['client'], rest = client.split(' ', 1)
            _trash, ret['clientVersion'] = rest.split(':', 1)
            
            if active == 'M:A':
                ret['active'] = True
            else:
                ret['active'] = False
            
            ret['hubsAsUser'], ret['hubsAsOp'], ret['hubsAsRegistered'] = hubs[2:].split('/')
            
            if ',' in slots:
                slots, miniSlots = slots.split(',', 1)
                ret['miniSlots'] = miniSlots[2:]
            ret['openSlots'] = slots[2:]
            
        for key in ('hubsAsUser', 'hubsAsOp', 'hubsAsRegistered', 'shareSize', 'openSlots'):
            if ret.has_key(key):
                ret[key] = int(ret[key])
    except MyInfoParseError:
        raise
    except Exception, ee:
        raise MyInfoParseError(ee)
    return ret
    
    
    