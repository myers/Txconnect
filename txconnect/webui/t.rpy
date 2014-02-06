from twisted.python import log
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.python.filepath import FilePath
import datetime, pprint

from txconnect.directconnect import interfaces

from django.db import models

from txconnect.trafficlog import models as trafficlog_models
from txconnect import dbthread, django_templates

def lowest_download_priority(byteCountByPriority):
    #self.config['daily_bandwith_limits']
    limits = {0: 1073741824, 100: 1073741824}
    limits = limits.items()
    limits.sort(key=lambda aa: aa[0])
    total = 0
    #for bcbp in byteCountByPriority:
        
        
        
    return pprint.pformat(byteCountByPriority)
    


class TrafficLogLastPage(Resource):
    isLeaf = True
    
    def render_GET(self, request):
        @dbthread.readQuery
        def _getByteCountByPriority():
            day_ago = datetime.datetime.now() - datetime.timedelta(days=1)
            qs = trafficlog_models.LogEntry.objects.filter(type='D', start__gte=day_ago).values('priority')
            qs = qs.annotate(size=models.Sum('actual_length'), count=models.Count('id'))
            qs = qs.order_by('priority')
            return list(qs)
        
        dd = _getByteCountByPriority()
                
        def _writeA(results):
            c = {
              'byte_count_by_priority': results,
              'lowest_download_priority': lowest_download_priority(results),
            }
            request.write(django_templates.render_string(OVERVIEW_TEMPLATE, c))
            request.finish()
        def _errorA(failure):
            request.write(str(failure))
            #log.err()
            request.finish()
        dd.addCallbacks(_writeA, _errorA)
        dd.addErrback(log.err)
        return NOT_DONE_YET
        
OVERVIEW_TEMPLATE = """
{% extends "simple.html" %}
{% block content %}
<h1>{% block title %}download traffic in the last 24 hours{% endblock %}</h1>

<p>{{lowest_download_priority}}</p>
<table>
<tr><th>priority</th><th>count</th><th>size</th></tr>
{% for nfo in byte_count_by_priority %}
<tr>
  <td>{{nfo.priority}}</td>
  <td>{{nfo.count}}</td>
  <td>{{nfo.size|filesizeformat}}</td>
</tr>
{% endfor %}
</table>
{% endblock %}
"""

resource = TrafficLogLastPage()
