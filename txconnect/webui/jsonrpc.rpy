import os

from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.python import log
from twisted.application.service import IServiceCollection
try:
    import json
except ImportError:
    import simplejson as json
import pprint

from txconnect.directconnect.peer import Peer
from txconnect.directconnect import interfaces
from django.db.models import Sum, Count
from txconnect.queuestore import models
from txconnect import dbthread, humanreadable, wsapi

encoder = wsapi.TxconnectJSONEncoder()
from txjsonrpc.web import jsonrpc

class ApiResource(jsonrpc.JSONRPC):
    """
    An example object to be published.
    """
    def jsonrpc_add(self, a, b):
        """
        Return sum of arguments.
        """
        return a + b
        
"""        
class ApiResource(Resource):
    def getChild(self, name, request):
        if name == 'download':
            page = DownloadPage()
        elif name == 'search':
            page = SearchPage()
        elif name == 'peers':
            page = PeersPage()
        elif name == 'peer':
            page = PeerPage()
        elif name == 'localSearch':
            page = LocalSearchPage()
        elif name == 'queueStore':
            page = QueueStorePage()
        elif name == 'shareStore':
            page = ShareStorePage()
        else:
            return
        page.application = self.application
        return page

class PeersPage(Resource):
    isLeaf = True
    
    def render_GET(self, request):
        request.setHeader('Content-type', 'application/json')
        peers = []
        for hub in interfaces.IHubHerder(self.application).allConnectedHubs():
            for peer, info in hub.peers.items():
                peers.append(peer)
        
        @dbthread.readQuery
        def _total():
            res3 = models.Source.objects.filter(peer__in=map(str, peers)).values('peer').annotate(Count('peer'))
            res3 = dict([(ii['peer'], ii['peer__count'],) for ii in res3])
            for peer in peers:
                if res3.has_key(str(peer)):
                    continue
                res3[str(peer)] = 0
            return res3
        dd = _total()
        def _printRes(results):
            request.write(encoder.encode(results))
            request.finish()
        def _error(error):
            request.finish()
        dd.addCallbacks(_printRes, _error)
        return NOT_DONE_YET

class PeerPage(Resource):
    isLeaf = True
    
    def render_GET(self, request):
        request.setHeader('Content-type', 'application/json')
        
        peerInfo = None
        for hub in interfaces.IHubHerder(self.application).allConnectedHubs():
            for peer, info in hub.peers.items():
                if str(peer) == request.args["peer"][0]:
                    peerInfo = info
        encoder = wsapi.TxconnectJSONEncoder()
        return encoder.encode(peerInfo)

class LocalSearchPage(Resource):
    isLeaf = True
    
    def render_GET(self, request):
        request.setHeader('Content-type', 'application/json')
        fileSource = interfaces.IFileSource(self.application)
        if request.args.has_key('filetype'):
            filetype = request.args["filetype"][0]
        else:
            filetype = 1 
        dd = fileSource.search(request.args["term"][0], filetype=filetype)
        def _printRes(results):
            request.write(encoder.encode(results))
            request.finish()
        def _error(error):
            request.finish()
        dd.addCallbacks(_printRes, _error)
        return NOT_DONE_YET

    
class SearchPage(Resource):
    isLeaf = True

    def render_GET(self, request):
        request.setHeader('Content-type', 'application/json')
        #request.setHeader('Content-type', 'text/plain')
        searchHerder = interfaces.ISearchHerder(self.application)
        kwargs = dict([(arg, val[0],) for arg, val in request.args.items()])
        kwargs['term'] = kwargs['term'].decode('utf-8')
        if 'priority' in kwargs:
            kwargs['priority'] = int(kwargs['priority'])
        dd = searchHerder.searchWithResults(**kwargs)
        def _cancel(failure):
            dd.cancel()
        request.notifyFinish().addErrback(_cancel)
        def _afterSearch(results):
            results = list(results)
            for result in results:
                if result.has_key('peer'):
                    result['peer'] = str(result['peer'])
                try:
                    encoder.encode(result)
                except UnicodeDecodeError, ee:
                    print ee
                    print "%r" % (result,)
                    results.remove(result)
                    
            
            request.write(encoder.encode(results))
            #request.write(pprint.pformat(list(results)))
            request.finish()
        def _error(failure):
            request.setResponseCode(500)
            request.write(str(failure))
            request.finish()
        dd.addCallbacks(_afterSearch, _error)
        return NOT_DONE_YET

class DownloadPage(Resource):
    isLeaf = True
        
    def render_POST(self, request):
        kwargs = json.loads(request.content.read())
        for key in kwargs.keys():
            kwargs[key.encode('utf-8')] = kwargs.pop(key)
        
        plainSources = kwargs.pop('sources')
        kwargs['sources'] = {}
        if plainSources:
            for peer, path in plainSources.items():
                kwargs['sources'][Peer(peer)] = path

        if not kwargs.has_key('priority'):
            kwargs['priority'] = 0

        fileSource = interfaces.IFileSource(self.application)
        downloadQueue = interfaces.IDownloadQueue(self.application)

        def _download():
            dd = downloadQueue.download(**kwargs)
            def _afterQueue(res):
                if res:
                    request.write(encoder.encode({'results': 'ok'}))
                else:
                    request.write(encoder.encode({'results': 'duplicate'}))
                request.finish()
            def _afterQueueError(err):
                log.err(err)
                request.write(encoder.encode({'results': 'fail'}))
                request.finish()
            dd.addCallbacks(_afterQueue, _afterQueueError)
        
        if kwargs['tth']:
            dd = fileSource.haveFileWithTTH(kwargs['tth'])
            
            def _downloadIfNotDuplicate(duplicate):
                if duplicate:
                    request.write(encoder.encode({'results': 'downloaded'}))
                    request.finish()
                    return
                _download()
            dd.addCallbacks(_downloadIfNotDuplicate, log.err)
            dd.addErrback(log.err)
        else:
            _download()
        return NOT_DONE_YET

class ShareStorePage(Resource):
    isLeaf = True
  
    def render_POST(self, request):
        request.setHeader('Content-type', 'application/json')
        if request.args.has_key('start'):
            fileSource = interfaces.IFileSource(self.application)
            fileSource.startIndexer()
        return encoder.encode({'status': 'ok'})

from txconnect.queuestore import models as queuestore_models

class QueueStorePage(Resource):
    isLeaf = True

    def render_GET(self, request):
        request.setHeader('Content-type', 'application/json')
        @dbthread.readQuery
        def _all_files():
            res = []
            for ff in list(queuestore_models.File.objects.all().select_related()): #.order_by('-file__priority')):
                res.append(ff.outpath)
            return res
                  
        dd = _all_files()
        def _write(results):
            request.write(encoder.encode(results))
            #request.write(pprint.pformat(list(results)))
            request.finish()
        def _error(failure):
            request.setResponseCode(500)
            request.write(str(failure))
            request.finish()
        dd.addCallbacks(_write, _error)
        return NOT_DONE_YET

    def render_POST(self, request):
        request.setHeader('Content-type', 'application/json')
        kwargs = json.loads(request.content.read())
        outfilepath = kwargs['outfilepath']
        @dbthread.writeQuery
        def _cancel():
            ff = queuestore_models.File.objects.get(directory=os.path.dirname(outfilepath), name=os.path.basename(outfilepath))
            ff.delete()
        def _write(results):
            request.write(encoder.encode({'status': 'ok'}))
            #request.write(pprint.pformat(list(results)))
            request.finish()
        def _error(failure):
            log.msg(str(failure))
            request.setResponseCode(500)
            request.write(str(failure))
            request.finish()
        
        dd = _cancel()
        dd.addCallbacks(_write, _error)
        return NOT_DONE_YET
"""

resource = ApiResource()
