from twisted.web.resource import Resource
from twisted.python.filepath import FilePath
from twisted.web.server import NOT_DONE_YET
import datetime

from txconnect.directconnect import interfaces
from txconnect import django_templates

class DownloaderManagerPage(Resource):
    isLeaf = True

    def render_GET(self, request):
        downloaderManager = interfaces.IDownloaderManager(self.application)
        peerHerder = interfaces.IPeerHerder(self.application)

        def _gah(val):
            if val:
                return val
            return datetime.datetime.now()        
        downloaders = downloaderManager.downloaders.values()
        downloaders.sort(lambda aa, bb: cmp(_gah(aa.startedAt), _gah(bb.startedAt)))
        c = {
          'startedAt': downloaderManager.startedAt,
          'downloaders': downloaders,
          'peerCheckout': peerHerder._peerCheckout,
          'peerStatus': peerHerder.peerStatus,
          'downloadConnections': peerHerder.downloadConnections
        }
        
        return django_templates.render_string(TEMPLATE, c)

    def render_POST(self, request):
        action = request.args['action'][0]
        downloadId = int(request.args['downloadId'][0])
        downloaderManager = interfaces.IDownloaderManager(self.application)
        def _after(res):
            request.redirect(request.uri)
            request.finish()
        def _error(err):
            request.finish()
        
        if action == 'delete':
            dd = downloaderManager.cancelDownload(downloadId)
            dd.addCallbacks(_after, _error)
            return NOT_DONE_YET
        else:
            downloaderManager.pauseDownload(downloadId)
            _after(None)
        
        
TEMPLATE = """
{% extends "simple.html" %}
{% load utils %}
{% block content %}
<h1>{% block title %}downloaders ({{downloaders|length}}){% endblock %}</h1>
(started {{startedAt|timesince}} ago)
<table>
<thead>
  <tr>
    <td>Status</td>
    <td>File</td>
    <td>Searched</td>
    <td>Multi</td>
    <td>Size</td>
    <td>Blocks</td>
    <td>Action</td>
  </tr>
</thead>
<tbody>
{% for dler in downloaders %}
    <tr class="{% cycle 'odd' 'even' %}{% if dler.active %} active{% endif %}">
      <td>{{dler.id}}<br />{{dler.download.id}}<br />{{dler.status}}<br />{{dler.startedAt|timesince}}</td>
      <td>
      {{dler.download.outfilepath}}<br />
      {{dler.download.label}}<br />
      {{dler.download.tth}}<br />
      Active:
      <ul>
      {% regroup dler.peerStatus.keys|attrsort:'hubId' by hubId as hub_list %}
      {% for hub in hub_list %}
        <li>{{ hub.grouper }}<ul>
        {% for peer in hub.list %}
          {% with info=dler.peerStatus|get_item:peer %}
          <li class="{{info.status|slugify}}">
              <a href="/peers/{{peer}}/">{{ peer.nick }}</a>: {{ info.status}} {% if info.more %}M:{{info.more.maxed}} T:{{info.more.timeout}} S:{{info.more.openSlots}} U:{{info.more.updatedAt|timesince}}{% endif %}
              {% if info.blockCount %} 
                - {{ info.blockCount }} block{{ info.blockCount|pluralize }} assigned 
                - {{info.connection.currentTransfer.bytesTransfered|filesizeformat}} of {{info.connection.currentTransfer.bytesToTransfer|filesizeformat}} @ {{ info.connection.currentTransfer.rate|filesizeformat }}/s{% endif %}
          </li>
          {% endwith %}
        {% endfor %}
        </ul></li>
      {% endfor %}
      </ul>
      
      </td>
      <td>
        {% if dler.searchStatus == 'searching' %}...<br />{{dler.searchStartedAt|timesince}}{% endif %}
        {% if dler.searchStatus == 'searched' %}x{% endif %}
        {{ dler.fileModel.last_searched_for_sources|timesince }}
      </td>
      <td>{% if dler.download.canMultisource %}M{% endif %}</td>
      <td>{{dler.bytesTransfered|filesizeformat}} / {{dler.download.size|filesizeformat}}</td>
      <td>{{dler.allDownloadingBlocks|length}} / {{dler.neededBlocks|length}}</td>
      <td>
        <form method="post">
          <input type="hidden" name="action" value="pause" />
          <input type="hidden" name="downloadId" value="{{dler.download.id}}" />
          <input type="submit" value="Pause" />
        </form>
        <br />
        <form class="delete-form" method="post">
          <input type="hidden" name="action" value="delete" />
          <input type="hidden" name="downloadId" value="{{dler.download.id}}" />
          <input type="submit" value="Delete" />
        </form>
      </td>
    </tr>
{% endfor %}
</table>
<script>
  $('.delete-form').submit(function() {
    return confirm("Are you sure you want to delete this download?");
  });
</script>    
<h1>peer status</h1>
<table>
<thead>
  <tr>
    <td>Nick</td>
    <td>Maxed</td>
    <td>Timeout</td>
    <td>Slots</td>
    <td>Updated</td>
  </tr>
</thead>
<tbody>
{% for peer, status in peerStatus.items %}
    <tr class="{% cycle 'odd' 'even' %} {% if peer in downloadConnections.keys %}online{% endif %}">
      <td>{{peer.nick}}</td>
      <td>{{status.maxed}}</td>
      <td>{{status.timeout}}</td>
      <td>{{status.openSlots}}</td>
      <td>{{status.updatedAt|timesince}}</td>
      <td>{% if peer in peerCheckout.keys %}*{% endif %}</td>
      
    </tr>
{% endfor %}
</table>

<!--
<h1>peer checkout</h1>
{% for peer, downloaders in peerCheckout.items %}
<h2>{{ peer.nick }}</h2>
<ul>
  {% for downloader in downloaders %}
   <li>{{ downloaders|pprint }}</li>
  {% endfor %}
</ul>
-->

{% endfor %}
{% endblock %}
"""

resource = DownloaderManagerPage()
