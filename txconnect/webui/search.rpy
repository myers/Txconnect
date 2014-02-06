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

class DownloaderManagerPage(Resource):
    isLeaf = True

    def render_GET(self, request):
        hubHerder = interfaces.IHubHerder(self.application)
        return django_templates.render_string(TEMPLATE, dict(hubHerder=hubHerder))

TEMPLATE = """
{% extends "simple.html" %}
{% block content %}
<h1>pending searches</h1>

{% for hub in hubHerder.hubs.values %}
<h2>{{ hub.id }}</h2>
<pre>
{{ hub.pendingSearches.pq|pprint }}
</pre>
{% endfor %}
{% endblock %}
"""

resource = DownloaderManagerPage()
