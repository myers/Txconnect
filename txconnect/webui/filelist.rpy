from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.python import log
from twisted.application.service import IServiceCollection
import pprint, cgi, urllib, urlparse, ntpath

from txconnect import dbthread, humanreadable, django_templates
from txconnect.directconnect import interfaces

class FilelistPage(Resource):
    isLeaf = True

    def render_GET(self, request):
        fileSource = interfaces.IFileSource(self.application)
        
        dd = fileSource.getFilesXmlBz2()
        def _printRes(results):
            request.write(results['fileobj'].read())
            request.finish()

        def _error(error):
            log.err()
            request.finish()
        dd.addCallbacks(_printRes, _error)
        dd.addErrback(_error)
        return NOT_DONE_YET

resource = FilelistPage()

