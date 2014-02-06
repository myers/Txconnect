from twisted.web.resource import Resource
from twisted.python import rebuild
from twisted.application.service import IServiceCollection
import pprint
import cgi 

class ServicesPage(Resource):
    isLeaf = True

    def render_GET(self, request):
        html = ['<html><body>']
        html += ['<h1>reload a service</h1>']
        html += ['<form method="post">']
        html += self.serviceTree(self.serviceRoot())
        html += ['</form>']
        #html += ['<form method="post"><input type="text" name="foo" /><input type="submit" value="bar" name="baz" /></form>']
        html += ['</body></html>']
        return ''.join(html)

    def serviceRoot(self):
        return IServiceCollection(self.application)

    def serviceTree(self, serviceCollection):
        ret = ['<ul>']
        for service in serviceCollection:
            q = service.name or '<unnamed>'
            ret += ['<li><strong>', cgi.escape(q), '</strong> ', cgi.escape(service.__module__)]
            ret += ['<input type="submit" value="' + cgi.escape(q) + '" name="reload" />']
            if IServiceCollection.providedBy(service):
                ret += self.serviceTree(service)
            ret += ['</li>']
        ret += ['</ul>']
        return ret

    def findServiceByName(self, serviceCollection, name):
        for service in serviceCollection:
            if service.name == name:
                return service
            if IServiceCollection.providedBy(service):
                service = self.findServiceByName(service, name)
                if service: 
                    return service
        return None
        
    def render_POST(self, request):
        service = self.findServiceByName(self.serviceRoot(), request.args['reload'][0])
        service.stopService()
        mod = __import__(service.__module__)
        rebuild.rebuild(mod)
        service.startService()
        
        request.redirect(request.uri)
        request.finish()

resource = ServicesPage()
