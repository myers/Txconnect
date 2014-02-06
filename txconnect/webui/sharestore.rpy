from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.python import log
from twisted.application.service import IServiceCollection
try:
    import json
except ImportError:
    import simplejson as json
import pprint, cgi, urllib, urlparse, ntpath

from txconnect import dbthread, humanreadable, django_templates
from txconnect.directconnect import interfaces

class SharestorePage(Resource):
    #isLeaf = False

    def __init__(self, path=''):
        Resource.__init__(self)
        self.path = path
        
    def getChild(self, path, request):
        child = SharestorePage(ntpath.join(self.path, path))
        child.application = self.application
        return child
    
    def render_GET(self, request):
        #return str(self.path)
        fileSource = interfaces.IFileSource(self.application)
        
        dd = fileSource.listPath(self.path[:-1])
        def _printRes(results):
            results.sort(lambda aa, bb: cmp(aa['name'], bb['name']))

            c = {
              'path': self.path,
              'results': results
            }
            
            request.write(django_templates.render_string(TEMPLATE, c))
            request.finish()

        def _error(error):
            log.err()
            request.finish()
        dd.addCallbacks(_printRes, _error)
        dd.addErrback(_error)
        return NOT_DONE_YET

TEMPLATE = """
{% extends "simple.html" %}
{% load utils %}
{% block content %}
<h1>{% block title %}sharestore: {{ path }}{% endblock %}</h1>
{% if path != '' %}
<a href="..">Up</a>
{% endif %}

<table width="100%">
{% for path in results %}
<tr>
  {% if path.filetype == 8 %}
    <td><a href="./{{path.name|escape_hash}}/">{{path.name}}</a></td><td></td><td></td>
  {% else %}
    <td>{{path.name}}</td><td>{{path.size}}</td><td>{{path.tth}}</td>
  {% endif %}
</tr>
{% endfor %}
</table>
{% endblock %}
"""

resource = SharestorePage()
