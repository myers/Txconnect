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
        
        dd = sharestore.getFilesXmlBz2(filter=["Comics"])
                
        def _writeA(results):
            request.setHeader('Content-type', 'application/octet-stream')
            request.setHeader('Content-Disposition', 'attachment; filename="files.xml.bz2"')
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
<pre>{{ results|pprint }}</pre>
{% endblock %}
"""


resource = ShareStoreFileXmlBzPage()
