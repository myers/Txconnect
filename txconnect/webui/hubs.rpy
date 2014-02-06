from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.python import log
from twisted.application.service import IServiceCollection
import simplejson as json
import pprint, cgi, urllib, os

from django.db.models import Sum, Count
from txconnect.queuestore import models
from txconnect import dbthread, humanreadable, django_templates
from txconnect.directconnect import interfaces
from txconnect.directconnect.peer import Peer

class HubHerderPage(Resource):
    isLeaf = True

    def render_GET(self, request):
        hubHerder = interfaces.IHubHerder(self.application)
        config = interfaces.IConfig(self.application)
        hubs = config['hubs']
        c = {
          'hubHerder': hubHerder,
          'hubs': hubs,
        }
        
        html = django_templates.render_string(TEMPLATE, c)
        
        
        return html

    def render_POST(self, request):
        downloaderId = int(request.args['downloaderId'][0])
        downloaderManager = interfaces.IDownloaderManager(self.application)
        dler = downloaderManager.downloaders[downloaderId]
        dler.cancel()
        request.redirect(request.uri)
        request.finish()
        
TEMPLATE = """
{% extends "simple.html" %}
{% block style %}
  .active {background-color:sienna;}
  table, th, td { border: 1px solid black; }
  table { border-collapse:collapse; }
  
  .not-registered { text-decoration: line-through; }
  .offline { color: grey };
  
  tr {vertical-align:text-top;}
  tr.even {background-color: #eee;}
  tr.odd {background-color: #fff;}
  tr.active {background-color: #99FFCC; }
  tr.online {background-color: green;}
  table {width: 100%}
{% endblock %}

{% block content %}
<h1>Connected</h1>
{{ hubHerder.hubs|pprint }}
{% for hub in hubHerder.allConnectedHubs %}
  <pre>{{ hub.filter }}</pre>
{% endfor %}
<h1>Hub config</h1>
<pre>{{ hubs|pprint }}</pre>
{% endblock %}
"""

resource = HubHerderPage()
