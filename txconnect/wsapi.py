import datetime, ntpath, os

import louie
try:
    import json
    from json import JSONEncoder
except ImportError:
    import simplejson as json
    from simplejson.encoder import JSONEncoder

from twisted.python import log, failure
from twisted.internet import defer

from directconnect.peer import Peer
from directconnect import interfaces

import websocket

class WebUIHandler(websocket.WebSocketHandler):
    def __init__(self, transport, site):
        websocket.WebSocketHandler.__init__(self, transport, site)
        self.site = site
        self.setupDone = False
        self.encoder = TxconnectJSONEncoder()
        
    def setup(self):
        louie.connect(self.translator, 'hub:status')
        louie.connect(self.translator, 'hub:name')
        louie.connect(self.translator, 'hub:global_to')
        louie.connect(self.translator, 'hub:to')
        louie.connect(self.translator, 'hub:chat_room')
        louie.connect(self.translator, 'hub:sent_to')

        louie.connect(self.translator, 'hub:user:new')
        louie.connect(self.translator, 'hub:user:update')
        louie.connect(self.translator, 'hub:user:quit')

        louie.connect(self.translator, 'peer:new')
        louie.connect(self.translator, 'peer:quit')
        louie.connect(self.translator, 'peer:upload:start')
        louie.connect(self.translator, 'peer:upload:progress')
        louie.connect(self.translator, 'peer:upload:end')
        louie.connect(self.translator, 'peer:download:start')
        louie.connect(self.translator, 'peer:download:progress')
        louie.connect(self.translator, 'peer:download:end')

        louie.connect(self.translator, 'share_store:walking')
        louie.connect(self.translator, 'share_store:walking:done')
        louie.connect(self.translator, 'share_store:hashing')
        louie.connect(self.translator, 'share_store:hashed')
        louie.connect(self.translator, 'share_store:size')
        louie.connect(self.translator, 'share_store:indexer:finished')

        self.searchFilters = []

        for hubId, status in self.hubHerder.activeHubs.items():
            self.sendUI('hub:new', hubId)
            hub = self.hubHerder.hubs.get(hubId, None)
            if hub:
                self.sendUI('hub:name', hubId, hub.hubname)
                for peer, info in hub.peers.items():
                    self.sendUI('hub:user:new', hubId, peer.nick, info['op'], info.get('info', ''))
        for connection in self.peerHerder.connections:
            self.sendUI('peer:new', id(connection), connection.remoteNick, connection.peer.hubId)
            if connection.currentTransfer:
                xfer = connection.currentTransfer
                self.sendUI('peer:' + xfer.type + ':start', id(connection), xfer.dcPath, *xfer.status())

        self.sendUI('share_store:size', size=self.fileSource.size, count=self.fileSource.count)

        for msg in self.memory.messages:
            self.sendUI(*msg)
        self.setupDone = True

    def connectionLost(self, reason):
        #FIXME: There's got to be a better way than this
        louie.disconnect(self.translator, 'hub:status')
        louie.disconnect(self.translator, 'hub:name')
        louie.disconnect(self.translator, 'hub:global_to')
        louie.disconnect(self.translator, 'hub:to')
        louie.disconnect(self.translator, 'hub:chat_room')
        louie.disconnect(self.translator, 'hub:sent_to')

        louie.disconnect(self.translator, 'hub:user:new')
        louie.disconnect(self.translator, 'hub:user:update')
        louie.disconnect(self.translator, 'hub:user:quit')

        louie.disconnect(self.translator, 'peer:new')
        louie.disconnect(self.translator, 'peer:quit')
        louie.disconnect(self.translator, 'peer:upload:start')
        louie.disconnect(self.translator, 'peer:upload:progress')
        louie.disconnect(self.translator, 'peer:upload:end')
        louie.disconnect(self.translator, 'peer:download:start')
        louie.disconnect(self.translator, 'peer:download:progress')
        louie.disconnect(self.translator, 'peer:download:end')

        louie.disconnect(self.translator, 'share_store:walking')
        louie.disconnect(self.translator, 'share_store:walking:done')
        louie.disconnect(self.translator, 'share_store:hashing')
        louie.disconnect(self.translator, 'share_store:hashed')
        louie.disconnect(self.translator, 'share_store:size')
        louie.disconnect(self.translator, 'share_store:indexer:finished')
       
    @property
    def searchHerder(self):
        return interfaces.ISearchHerder(self.site.application)

    @property
    def fileSource(self):
        return interfaces.IFileSource(self.site.application)

    @property
    def hubHerder(self):
        return interfaces.IHubHerder(self.site.application)

    @property
    def peerHerder(self):
        return interfaces.IPeerHerder(self.site.application)

    @property
    def downloadQueue(self):
        return interfaces.IDownloadQueue(self.site.application)

    @property
    def memory(self):
        return interfaces.IMessageMemory(self.site.application)

    def translator(self, *args, **kwargs):
        sig = kwargs.pop('signal')
        kwargs.pop('sender')
        #msg = [signal] + list(args)
        self.sendUI(sig, *args, **kwargs)

    def frameReceived(self, data):
        if data != '["hello"]':
            log.msg(data)
        if not self.setupDone:
            self.setup()
        
        try:
            data = json.loads(data)
        except ValueError:
            return
        if data[0] == 'hello':
            return
        elif data[0] == 'call':
            callId, method, args = data[1:]
            cmd = getattr(self, 'cmd_%s' % (method.replace(':', '_'),), None)
            if not cmd:
                self.sendUI('exception', callId, 'no such method %r' % (method,))
                return
            def _returnCall(res):
                assert isinstance(callId, int), "%r" % (callId,)
                self.sendUI('return', callId, res)
            def _errorCall(failure):
                assert isinstance(callId, int), "%r" % (callId,)
                failure.printTraceback()
                self.sendUI('exception', callId, str(failure))

            try:
                dd = defer.maybeDeferred(cmd, *args)
                dd.addCallbacks(_returnCall, _errorCall)
                dd.addErrback(log.err)
            except:
                _errorCall(failure.Failure())
        else:
            raise Exception, "do not know how to handle %r" % (data,)

    def onSearchResult(self, *args, **kwargs):
        try:
            searchFilter = kwargs.pop('sender')
            del kwargs['signal']
            kwargs['peer'] = str(kwargs['peer'])
            self.sendUI('search:result', id(searchFilter), kwargs)
        except Exception, e:
            print 'error in onSearchResult', e
        
    def sendUI(self, *args, **kwargs):
        try:
            msg = list(args)
            if len(kwargs):
                msg += [kwargs]
            self.transport.write(self.encoder.encode(msg))
        except Exception, ee:
            print 'error sending %r %r %r' % (args, kwargs, ee,)

    def cmd_download_outpaths(self, *args):
        return self.downloadQueue.outpaths(*args)
        
    def cmd_download_filesForOutpath(self, *args):
        return self.downloadQueue.filesForOutpath(*args)
        
    def cmd_download(self, peer, filepath, type, tth, size):
        #def download(outfile, tth=None, size=None, type='file', offset=0, priority=10, sources=None):
        peer = Peer(peer)
        outfile = os.path.join(peer.nick, ntpath.basename(filepath))
        return self.downloadQueue.download(outfile, tth=tth, size=size, priority=100, type=type, sources={peer: filepath})

    def cmd_search(self, term, kwargs):
        # the keys will be unicode() objects
        kwargs = dict([(str(key), item) for key, item in kwargs.items()])
        kwargs['priority'] = 100

        times, searchFilter = self.searchHerder.search(term, **kwargs)
        self.searchFilters.append(searchFilter)
        louie.connect(self.onSearchResult, 'search:result', searchFilter)
        return [id(searchFilter), times]
    
    def cmd_search_delete(self, idOfFilter):
        for sf in self.searchFilters:
            if id(sf) == idOfFilter:
                louie.disconnect(self.onSearchResult, 'search:result', sf)
                sf.cancel()                
                self.searchFilters.remove(sf)
                break

    def cmd_say(self, hubId, msg):
        hub = self.hubHerder.hubs[hubId]
        hub.say(msg)

    def cmd_indexer_start(self):
        self.fileSource.startIndexer()

    def cmd_to(self, peer, msg):
        peer = Peer(peer)
        hub = self.hubHerder.hubs[peer.hubId]
        hub.sendMessage(peer, msg)
        return hub.nick, datetime.datetime.utcnow().isoformat(), msg

class TxconnectJSONEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, Peer):
            return str(obj)
        elif isinstance(obj, failure.Failure):
            return str(obj)
        return JSONEncoder.default(self, obj)
