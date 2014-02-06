from twisted.internet import defer
from twisted.python import log
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.python.filepath import FilePath
import datetime

from txconnect.directconnect import interfaces
from txconnect import django_templates

from django.db import models

class ShareStoreFileXmlBzPage(Resource):
    def getChild(self, path, request):
        if path == '':
            return self
    def render_GET(self, request):
        sharestore = interfaces.IFileSource(self.application)
        
        if request.args.has_key('s'):
            dd = sharestore.search(request.args['s'][0])
        else:
            dd = defer.succeed([])
                
                
        def _writeA(results):
            request.write(django_templates.render_string(FILE_TEMPLATE, dict(results=results)))
            request.finish()
        def _errorA(failure):
            request.write(str(failure))
            #log.err()
            request.finish()
        dd.addCallbacks(_writeA, _errorA)
        dd.addErrback(log.err)
        return NOT_DONE_YET
        
FILE_TEMPLATE = """
{% extends "simple.html" %}
{% block content %}
<form>
<input type="text" name="s" />
<button type="submit">search</button>
</form>
{% if results %}
  <table>
    <tr><th>path</th><th>size</th></tr>
    {% for res in results %}
      <tr><td>{{ res.0 }}</td><td>{{ res.1 }}</td></tr>
    {% endfor %}
  </table>
  {% endif %}
{% endblock %}
"""


resource = ShareStoreFileXmlBzPage()
