from twisted.web.resource import Resource
from twisted.python import rebuild
from twisted.application.service import IServiceCollection
import pprint, cgi, urllib
from twisted.python.filepath import FilePath

from txconnect import django_templates

class UploadQueuePage(Resource):
    isLeaf = True

    def render_GET(self, request):
        request.setHeader("Content-type", 'text/html; charset=UTF-8')
        peerHerder = self.findServiceByName(self.serviceRoot(), 'peerHerder')
        
        items = peerHerder._uploadQueue

        return django_templates.render_string(OVERVIEW_TEMPLATE, dict(items=items))

    def serviceRoot(self):
        return IServiceCollection(self.application)

    def findServiceByName(self, serviceCollection, name):
        for service in serviceCollection:
            if service.name == name:
                return service
            if IServiceCollection.providedBy(service):
                service = self.findServiceByName(service, name)
                if service: 
                    return service
        return None

OVERVIEW_TEMPLATE = """
{% extends "simple.html" %}
{% block content %}
<h1>{% block title %}upload queue{% endblock %}</h1>
<table>
<tr><th>peer</th><th>last attempt</th></tr>
{% for peer, lastAttempt in items %}
<tr>
  <td>{{ peer|pprint }}</td>
  <td>{{ lastAttempt|timesince }}</td>
</tr>
{% endfor %}
</table>
{% endblock %}
"""


resource = UploadQueuePage()
