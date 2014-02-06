from twisted.python import log
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.python.filepath import FilePath
import datetime

from txconnect.directconnect import interfaces

from django.db import models

from txconnect.queuestore import models as queuestore_models
from txconnect import dbthread, django_templates

class QueueOverviewPage(Resource):
    def getChild(self, path, request):
        if path == '':
            return self
        child = QueueByLabelPage(label=path)
        child.application = self.application
        return child

    def render_GET(self, request):
        @dbthread.readQuery
        def _getSizeByPriority():
            ret = {}
            for label in queuestore_models.Label.objects.all():
                ret[label.label] = label.file_set.values('priority').annotate(size=models.Sum('size'), count=models.Count('id')).order_by('-priority')
            ret[None] = queuestore_models.File.objects.filter(label=None).values('priority').annotate(size=models.Sum('size'), count=models.Count('id')).order_by('-priority')
            for key in ret.keys():
                if len(ret[key]) == 0:
                    del ret[key]
            return ret
        
        dd = _getSizeByPriority()
                
        def _writeA(results):
            c = {
              'size_by_priority': sorted(results.items())
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
<h1>{% block title %}download queue{% endblock %}</h1>
{% for label, label_nfo in size_by_priority %}
<h3>{{label}}</h3>
<table>
<tr><th>priority</th><th>count</th><th>size</th></tr>
{% for nfo in label_nfo %}
<tr>
  <td><a href="{{label}}/{{nfo.priority}}/">{{nfo.priority}}</a></td>
  <td>{{nfo.count}}</td>
  <td>{{nfo.size|filesizeformat}}</td>
</tr>
{% endfor %}
</table>
{% endfor %}
{% endblock %}
"""

class QueueByLabelPage(Resource):
    def getChild(self, path, request):
        if path == '':
            return self
        child = QueueByPriorityPage(label=self.label, priority=int(path))
        child.application = self.application
        return child

    def __init__(self, label):
        Resource.__init__(self)
        self.label = label
    
class QueueByPriorityPage(Resource):
    isLeaf = True

    def __init__(self, label=None, priority=0):
        Resource.__init__(self)
        self.priority = priority
        self.label = label
        
    def render_GET(self, request):
        
        @dbthread.readQuery
        def _getFiles():
            qs = queuestore_models.File.objects.filter(priority=self.priority)
            if self.label == 'None':
                qs = qs.filter(label=None)
            else:
                qs = qs.filter(label__label=self.label)
            qs = qs.annotate(source_count=models.Count('source')).order_by('directory', 'name')
            return list(qs)
        
        dd = _getFiles()
                
        def _writeA(results):
            c = {
              'files': results,
              'label': self.label,
            }
            
            request.write(django_templates.render_string(QUEUE_BY_PRIORITY_TEMPLATE, c))
            request.finish()
        def _errorA(failure):
            request.write(str(failure))
            #log.err()
            request.finish()
        dd.addCallback(_writeA)
        dd.addErrback(log.err)
        return NOT_DONE_YET

    def render_POST(self, request):
        queueStore = interfaces.IDownloadQueue(self.application)
        downloaderManager = interfaces.IDownloaderManager(self.application)
        if request.args['action'][0] == 'delete':
            class Tmp:
                id = int(request.args['file_id'][0])
            dd = queueStore.remove(Tmp)
        elif request.args['action'][0] == 'start':
            dd = queueStore.getById(int(request.args['file_id'][0]))
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
        

QUEUE_BY_PRIORITY_TEMPLATE = """
{% extends "simple.html" %}
{% block content %}
<h1>{{ label }} {% block title %}download queue{% endblock %}</h1>
<table>
<tr>
  <th>filename</th>
  <th>size</th>
  <th>last searched</th>
  <th>sources</th>
  <th>created</th>
  <th>actions</th>
</tr>
{% for ff in files %}
<tr>
  <td>{{ff.outpath}}<br />{{ff.tth}}</a></td>
  <td>{{ff.size|filesizeformat}}</td>
  <td>{{ff.last_searched_for_sources|timesince}}</td>
  <td>{{ff.source_count}}</td>
  <td>{{ff.created|timesince}}</td>
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

resource = QueueOverviewPage()
