from twisted.python import log
from twisted.internet import protocol, reactor, defer
from twisted.application import service
from zope.interface import implements

import louie

from ..directconnect import DC_ENCODING
from . import utils, interfaces
from .peer import Peer
from .. import lru

class SearchHerder(service.Service):
    name = 'searchHerder'
    
    implements(interfaces.ISearchHerder)

    def __init__(self, locator):
        self.locator = locator
        self.searchResponseProtocol = None
        self.listeningPort = None
        self.tthCache = lru.LRU(1000)
    
    def log(self, msg):
        log.msg(msg, system=self.name)
        
    @property
    def config(self):
        return interfaces.IConfig(self.locator)
                
    @property
    def filesource(self):
        return interfaces.IFileSource(self.locator)

    @property
    def peerHerder(self):
        return interfaces.IPeerHerder(self.locator)

    @property
    def hubHerder(self):
        return interfaces.IHubHerder(self.locator)

    def startService(self):
        service.Service.startService(self)
        self.searchResponseProtocol = SearchResponseProtocol(self.locator)
        self.ip = self.config['networking']['external_ip']
        self.port = self.config['networking']['port']
        self.listeningPort = reactor.listenUDP(self.port, self.searchResponseProtocol)

    def stopService(self):
        service.Service.stopService(self)
        return self.listeningPort.stopListening()
        
    def search(self, term, hubIds=None, maxsize=None, minsize=None, filetype=1, priority=0):
        self.log('search: term = %(term)r priority = %(priority)r' % locals())
        if hubIds is None:
            hubIds = self.hubHerder.hubs.keys()
        if not hubIds:
            raise Exception('no hubs to search on')
        ret = []
        if filetype == 9 and not term.startswith('TTH:') and len(term) == 39:
            term = "TTH:%s" % (term,)
        assert term != 'TTH:None', 'where is this coming from'
        sf = SearchFilter(term, hubIds=hubIds, maxsize=maxsize, minsize=minsize, filetype=filetype)
        for hubId in hubIds:
            hub = self.hubHerder.hubs[hubId]
            timeTilSearch, dd = hub.search(term, maxsize, minsize, filetype, priority)
            sf.addDeferred(dd)
            ret.append(timeTilSearch)
        return ret, sf

    def searchWithResults(self, term, wait=10, **kwargs):
        times, searchFilter = self.search(term, **kwargs)
        searchResults = SearchResults(searchFilter)
        def _afterSearchStarted(res):
            self.log('search sent on all hubs for %r' % (term,))
            dd = defer.Deferred()
            def _afterSearch():
                self.log('returning search results %r' % (term,))
                dd.callback(searchResults)
            reactor.callLater(wait, _afterSearch)
            return dd
        return searchFilter.searchStarted.addCallback(_afterSearchStarted)
    
    """
    Called by hubs when other hubclients want to search our local share
    
    @param hub where this search came from
    @param query dict with keys 'term', 'minsize', 'maxsize', 'filetype', 'peer', 'hub'
    """
    def localSearch(self, hub, query):
        # ignore queries from myself
        ip, port = query['peer'].split(':')
        if ip == self.ip and int(port) == self.port:
            return
        dd = self.filesource.search(
            term=query['term'],
            minsize=query['minsize'],
            maxsize=query['maxsize'],
            filetype=query['filetype'],
            filter=hub.filter)
        def _(res):
            self._respondToSearch(query['peer'], query['hub'], res)
        dd.addCallbacks(_, self.err)

    def err(self, res):
        print 'Error: %r' % dir(res)
        res.printTraceback()

    def _respondToSearch(self, peer, hub, res):
        if not res:
            return
        seachResults = []
        for ii in res[:10]:
            if ii[1] is None: # this is a directory
                seachResults.append('$SR %s %s %d/%d\x05%s (%s:%s)' % (hub.nick, ii[0].encode(DC_ENCODING), self.peerHerder.unusedSlots, self.peerHerder.maxSlots, hub.hubname, hub.hubAddr[0], hub.hubAddr[1],))
            else:
                seachResults.append('$SR %s %s\x05%s %d/%d\x05TTH:%s (%s:%s)' % (hub.nick, ii[0].encode(DC_ENCODING), ii[1], self.peerHerder.unusedSlots, self.peerHerder.maxSlots, ii[2].encode(DC_ENCODING), hub.hubAddr[0], hub.hubAddr[1],))
        for sr in seachResults:
            if peer.startswith('Hub:'):
                dest = peer.split(':', 1)[1]
                hub.sendLine('%s\x05%s' % (sr, dest,))
            else:
                try:
                    self.searchResponseProtocol.send(sr, utils.parseAddr(peer))
                except UnicodeEncodeError:
                    self.log("UnicodeEncodeError: %r %r" % (sr, peer,))
                    raise

class SearchFilter(object):
    def __init__(self, term, hubIds=None, maxsize=None, minsize=None, filetype=1):
        self.term = term 
        self.hubIds = hubIds
        self.maxsize = maxsize
        self.minsize = minsize
        self.filetype = filetype
        self.deferreds = []
        louie.connect(self.filter, 'search:result:raw')

    def addDeferred(self, dd):
        self.deferreds.append(dd)
  
    @property
    def searchStarted(self):
        if not hasattr(self, '_searchStarted'):
            self._searchStarted = defer.DeferredList(self.deferreds)
            # HACK: DeferredList has no way to set a cancel callable
            self._searchStarted._canceller = self.cancel
        return self._searchStarted
        
    def cancel(self, deferred=None):
        log.msg('CANCELING %r' % (self,))
        louie.disconnect(self.filter, 'search:result:raw')
        for dd in self.deferreds:
            dd.cancel()
    
    def filter(self, *args, **kwargs):
        # TODO: filter on filetype, max/min size, hubId
        del kwargs['sender']
        del kwargs['signal']
        
        if self.filetype == 9:
            if not kwargs['tth'] or not self.term.endswith(kwargs['tth']):
                #print self, 'filtering out %r' % (kwargs['filepath'],)
                return
        else:
            for termpart in self.term.lower().split(' '):
                if termpart not in kwargs['filepath'].lower():
                    #print self, 'filtering out %r' % (kwargs['filepath'],)
                    return
        louie.send('search:result', self, *args, **kwargs)        

    def __repr__(self):
        return '<SearchFilter %s: term %r>' % (id(self), self.term,)

class SearchResults:
    def __init__(self, searchFilter):
        self.searchFilter = searchFilter
        louie.connect(self.onSearchResult, 'search:result', searchFilter)
        self.results = []

    def onSearchResult(self, *args, **kwargs):
        del kwargs['signal']
        del kwargs['sender']
        self.results.append(kwargs)
        
    def __iter__(self):
        self.results.sort(lambda xx, yy: cmp(yy['slots'][0], xx['slots'][0]))
        return self.results.__iter__()
    
    def __len__(self):
        return self.results.__len__()

class SearchResponseProtocol(protocol.DatagramProtocol):
    def __init__(self, locator):
        self.locator = locator
    
    @property
    def hubHerder(self):
        return interfaces.IHubHerder(self.locator)
        
    def send(self, msg, addr):
        log.msg('%r >>> %r' % (addr, msg,))
        self.transport.write(msg, addr)
        
    # Possibly invoked if there is no server listening on the
    # address to which we are sending.
    def connectionRefused(self):
        print 'Noone listening'

    def datagramReceived(self, data, (host, port)):
        print '%s:%d <<< %r' % (host, port, data)
        try:
            if data[0] == '$':
                cmd, data = data[1:-1].split(' ', 1)
            elif data.startswith('UPSR'):
                # this is a partial search result from ApexDC/StrongDC.  It's sent when
                # they only have part of the file
                return
            else:	
                raise ValueError
        except ValueError, ee:
            log.err('deformed packet %r: %r' % (data, ee,))
            return
              
        phandler = getattr(self, 'handle%s' % (cmd,), None)
        if phandler:
            data = phandler(data, host, port)

    def handleSR(self, line, host, port):
        res = parseSearchResults(line)
        # is there some other way this could get want it needs without looking at the getPeer()?
        for hubProtocol in self.hubHerder.allConnectedHubs():
            hubaddr = hubProtocol.transport.getPeer()
            if res['hubaddr'][0] == hubaddr.host and res['hubaddr'][1] == hubaddr.port:
                res['peer'] = Peer(res['nick'], hubProtocol.id)
        if not res.has_key('peer'):
            log.msg('unknown hub for %r, ignoring %r' % (res, [hubProtocol.transport.getPeer() for hubProtocol in self.hubHerder.allConnectedHubs()],))
            return
        res['udp_sender'] = (host, port,)
        louie.send('search:result:raw', self, **res)

def parseSearchResults(line):
    res = dict(type='file')
    nick, rest = line.split(' ', 1)
    assert '\x05' in rest
    rest, tail = rest.rsplit('\x05', 1)
    if tail.startswith('TTH:'):
        res['tth'], tail = tail[len('TTH:'):].split(' (', 1)
        res['hubname'] = None
    else:
        res['tth'] = None
        res['hubname'], tail = tail.split(' (', 1)
    host, port = utils.parseAddr(tail.replace(')',''))
    res['hubaddr'] = (host, port,)
    res['nick'] = nick.decode(DC_ENCODING)

    rest, res['slots'] = rest.rsplit(' ', 1)
    res['slots'] = tuple(map(int, res['slots'].split('/')))
    
    if '\x05' in rest:
        res['type'] = 'file'
        res['filepath'], rest = rest.split('\x05', 1)
        res['filepath'] = res['filepath'].decode(DC_ENCODING)
        res['size'] = int(rest)
    else:
        res['type'] = 'directory'
        res['filepath'] = rest.decode(DC_ENCODING)
    
    return res    
        