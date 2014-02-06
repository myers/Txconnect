from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.python import log
from twisted.python.filepath import FilePath
from twisted.application.service import IServiceCollection
from twisted.internet.defer import DeferredList
import simplejson as json
import pprint, cgi, urllib, os

from django.db.models import Sum, Count
from txconnect.queuestore import models
from txconnect import dbthread, humanreadable, django_templates
from txconnect.directconnect import interfaces
from txconnect.directconnect.peer import Peer

class QueuestorePage(Resource):
    isLeaf = True

    def render_GET(self, request):
        if request.args.has_key('peer'):
            return self.files_for_peer(request, request.args['peer'][0])

        peers = []
        for hub in interfaces.IHubHerder(self.application).allConnectedHubs():
            for peer, info in hub.peers.items():
                peers.append(peer)
        
        @dbthread.readQuery
        def _total():
            res1 = models.File.objects.aggregate(Count('size')).values()[0]
            res2 = models.File.objects.aggregate(Sum('size')).values()[0]
            res3 = models.Source.objects.filter(peer__in=map(str, peers)).values('peer').annotate(Count('peer'))
            res3 = dict([(Peer(ii['peer']), ii['peer__count'],) for ii in res3])
            return res1, res2, res3

        dd = _total()
        def _printRes(results):
            fileCount, fileSize, sourcesByPeer = results
            sourcesByPeer = sourcesByPeer.items()
            sourcesByPeer.sort(key=lambda aa: aa[1])
            c = {
              'fileCount': fileCount,
              'fileSize': fileSize,
              'sourcesByPeer': sourcesByPeer,
            }
            
            request.write(django_templates.render_string(MAIN_TEMPLATE, c))
            request.finish()

        def _error(error):
            request.finish()
        dd.addCallbacks(_printRes, _error)
        return NOT_DONE_YET


    @dbthread.readQuery
    def lookup_files_for_peer(self, peerStr):
        res = []
        for src in list(models.Source.objects.filter(peer=peerStr).select_related().order_by('-file__priority')):
            try:
                ff = src.file
                count = ff.source_set.count()
                res.append((ff, count,))
            except models.File.DoesNotExist:
                src.delete()
        return res

    def files_for_peer(self, request, peerStr):
        dd = self.lookup_files_for_peer(peerStr)
        def _write(files):
            request.write(django_templates.render_string(PEER_TEMPLATE, dict(files=files)))
            request.finish()
            
        def _error(error):
            request.finish()
        dd.addCallbacks(_write, _error)
        return NOT_DONE_YET

    def render_POST(self, request):
        queueStore = interfaces.IDownloadQueue(self.application)
        downloaderManager = interfaces.IDownloaderManager(self.application)
        if request.args['action'][0] == 'delete_all':
            dd = self.lookup_files_for_peer(request.args['peer'][0])
            def cancel_all(files):
                return DeferredList([downloaderManager.cancelDownload(ff.id) for ff, count in files])
            dd.addCallback(cancel_all)
        elif request.args['action'][0] == 'delete':
            downloadId = int(request.args['file_id'][0])
            dd = downloaderManager.cancelDownload(downloadId)
        elif request.args['action'][0] == 'start':
            downloadId = int(request.args['file_id'][0])
            dd = queueStore.getById(downloadId)
            dd.addCallback(downloaderManager.startDownloader, force=True)
       
        def _writeA(results):
            request.redirect(request.uri)
            request.finish()
        def _errorA(failure):
            request.write(str(failure))
            #log.err()
            request.finish()
        dd.addCallbacks(_writeA, _errorA)
        dd.addErrback(log.err)
        return NOT_DONE_YET
        
MAIN_TEMPLATE = """
{% extends "simple.html" %}
{% block content %}
<h1>{% block title %}download queue{% endblock %}</h1>
<p>{{ fileCount }} / {{ fileSize|filesizeformat }}</p>

<table>
  <thead>
    <tr>
      <td>nick</td>
      <td>count</td>
    </tr>
  </thead>
  <tbody>
  {% for peer, count in sourcesByPeer %}
    <tr class="%s">
      <td><a href="?peer={{peer}}">{{peer.nick}}</a></td>
      <td>{{count}}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
"""            

PEER_TEMPLATE = """
{% extends "simple.html" %}
{% block content %}
<h1>{% block title %}download queue{% endblock %}</h1>
  <form method="post">
    <input type="submit" name="action" value="delete_all" />
  </form>

  <table>
  {% for ff, count in files %}
  <tr>
    <td>{{ count }}</td>
    <td>{{ ff.outpath }}<br/>{{ ff.tth }} ({{ ff.size }})</td>
    <td>{{ ff.last_searched_for_sources|timesince }}</td>
    <td>
      <form method="post">
        <input type="hidden" name="file_id" value="{{ ff.id }}" />
        <input type="submit" name="action" value="start" />
      </form>
      <form method="post">
        <input type="hidden" name="file_id" value="{{ ff.id }}" />
        <input type="submit" name="action" value="delete" />
      </form>
    </td>
  </tr>
  {% endfor %}
  </table>
{% endblock %}
"""


    
resource = QueuestorePage()
