from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.python import log
from twisted.application.service import IServiceCollection
import pprint
import cgi 
from django.db.models import Count

from txconnect import dbthread
from txconnect.sharestore import models

class AgePage(Resource):
    isLeaf = True

    def render_GET(self, request):
        dd = self.data()
        def _(res):
            html = ['<html><body><h1>how long have files been in share grouped by month</h1><pre>']
            html += [cgi.escape(pprint.pformat(res))]
            html += ['</pre></body></html>']
            request.write(''.join(html))
            request.finish()
        dd.addCallbacks(_, log.err)
        return NOT_DONE_YET

    @dbthread.readQuery
    def data(self):
        #data = models.Path.objects.dates('mtime', 'month')
        return models.Path.objects.extra(select={'date': 'django_date_trunc("month", "sharestore_path"."mtime")'}).values('date').annotate(num_files=Count('id'))
        """
        months = {}
        for date in data:
            
        for moth
        currentMonth = min(data)



        return min(data)
        """

resource = AgePage()
