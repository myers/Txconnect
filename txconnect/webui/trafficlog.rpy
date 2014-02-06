import datetime

from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET 
from twisted.python.filepath import FilePath
from twisted.python import log

from txconnect.directconnect import interfaces
from txconnect.trafficlog import models
from txconnect import dbthread, django_templates
from txconnect.directconnect.peer import Peer

from django.db.models import Sum

class TrafficLogPage(Resource):
    isLeaf = True

    def render_GET(self, request):
        @dbthread.readQuery
        def _getData():
            #limit = datetime.datetime.now() - datetime.timedelta(days=1)
            now = datetime.datetime.now()
            limit = datetime.datetime(now.year, now.month, 1)
        
            downloads = list(models.LogEntry.objects.filter(type='D', start__gte=limit).values('peer').annotate(byteCount=Sum('actual_length')).order_by('peer'))
            ret = {}
            for ii in downloads:
                ret.setdefault(Peer(ii['peer']), dict(upload=0, download=0))
                ret[Peer(ii['peer'])]['download'] += ii['byteCount']                
                
            uploads = list(models.LogEntry.objects.filter(type='U', start__gte=limit).values('peer').annotate(byteCount=Sum('actual_length')).order_by('peer'))
            for ii in uploads:
                ret.setdefault(Peer(ii['peer']), dict(upload=0, download=0))
                ret[Peer(ii['peer'])]['upload'] += ii['byteCount']
                
            return ret
        
        dd = _getData()
        
        def _render(stats):
            stats = stats.items()
            totals = dict(upload=0, download=0)
            for peer, peer_stats in stats:
                totals['upload'] += peer_stats['upload']
                totals['download'] += peer_stats['download']
            

            c = {
              'stats': stats,
              'totals': totals,
            }
            
            request.write(django_templates.render_string(TEMPLATE, c))
            request.finish()
        def _error(failure):
            request.write('error')
            request.finish()
        
            log.err(failure)
            print "%r" % (failure,)
            #log.err()
            
        dd.addCallbacks(_render, _error)
        dd.addErrback(log.err)
        
        return NOT_DONE_YET

        
TEMPLATE = """
{% extends "simple.html" %}
{% block head %}
<style>
  .rawdata { display: none; }
</style>
{% endblock %}
{% block content %}
<h1>{% block title %}traffic log{% endblock %}</h1>
<p>Upload: {{ totals.upload|filesizeformat }}</p>
<p>Download: {{ totals.download|filesizeformat }}</p>
<table id="traffic_by_peer">
<thead>
<tr>
  <th>nick</th>
  <th>hub</th>
  <th>download</th>
  <th>upload</th>
</tr>
</thead>
<tbody>
{% for peer, peer_stats in stats %}
<tr>
  <td>{{ peer.nick }}</td>
  <td>{{ peer.hubId }}</td>
  <td>{{ peer_stats.download|filesizeformat }} <span class="rawdata">{{peer_stats.download}}</span></td>
  <td>{{ peer_stats.upload|filesizeformat }} <span class="rawdata">{{peer_stats.upload}}</span></td>
</tr>
{% endfor %}
</tbody>
</table>
<script>
$(document).ready(function() { 
  $("#traffic_by_peer").tablesorter({
    sortList: [[2,1]],
    textExtraction: function(node) {
      var raw = $(node).find('span.rawdata');
      if (raw.length > 0) {
        return raw.html();
      }
      return $(node).html();
    }
  }); 
}); 
</script>                
{% endblock %}
"""

resource = TrafficLogPage()
