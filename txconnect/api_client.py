#!/usr/bin/env python

import urllib, urllib2, urlparse
try:
    import json
except ImportError:
    import simplejson as json
    
class ApiClient(object):
    """
    @param apiUrl a url with embedded username and password
    """
    def __init__(self, apiRoot):
        self.apiRoot = apiRoot
        self.opener = self.make_opener()

    def make_opener(self):
        scheme, netloc, path, query, fragment = urlparse.urlsplit(self.apiRoot)
        assert '@' in netloc, 'need auth info embedded in url'
        username, rest = netloc.split(':', 1)
        password, netloc = rest.split('@', 1)
        self.apiRoot = urlparse.urlunsplit((scheme, netloc, path, query, fragment,))
        password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, self.apiRoot, username, password)
        auth_handler = urllib2.HTTPBasicAuthHandler(password_mgr)
        #auth_handler.add_password('txconnect', netloc, username, password)
        return urllib2.build_opener(auth_handler)    

    def apiUrl(self, path):
        return urlparse.urljoin(self.apiRoot, path)

    def request(self, path, query=None, post=None):
        data = None
        url = self.apiUrl(path)
        if post:
            url = urllib2.Request(self.apiUrl(path))
            url.add_header('Content-type', 'application/json')
            url.add_header('Accept', 'application/json')
            data = json.dumps(post)
        if query:
            url = self.apiUrl(path) + '?%s' % (urllib.urlencode(query),)
            #print url
        response = self.opener.open(url, data)
        if response.code != 200:
            raise RemoteError(response.read())
        body = response.read()
        try:
            results = json.loads(body)
        except ValueError:
            raise RemoteError("This is not json: %r" % (body,))
        return results
            
    def reindex(self):
        return self.request('shareStore', post={'start': True})

    def search(self, term, **kwargs):
        kwargs.update({'term': term})
        return self.request('search', query=kwargs)

    def localSearch(self, term, **kwargs):
        kwargs.update({'term': term})
        return self.request('localSearch', query=kwargs)

    def peers(self):
        return self.request('peers')

    def download(self, outfile, tth=None, size=None, downloadType='file', sources=None, priority=0, label=None):
        assert type(downloadType) is str
        if sources:
            assert type(sources) is dict
        return self.request('download', post=dict(
          outfile=outfile, 
          tth=tth, 
          size=size, 
          type=downloadType, 
          sources=sources, 
          priority=priority,
          label=label
        ))

    def all_downloads(self):
        return self.request('queueStore')

    def cancel_download(self, outfilepath):
        return self.request('queueStore', post=dict(outfilepath=outfilepath))

class RemoteError(StandardError):
    pass

if __name__ == '__main__':
    import sys, os, pprint
    from magnet_uri import MagnetUri
    
    if not os.environ.has_key('API_ROOT'):
        raise Exception('`API_ROOT` env var needs to be something like http://username:password@hostAndPort/api')
    
    client = ApiClient(os.environ['API_ROOT'])

    if sys.argv[1] == 'reindex':
        pprint.pprint(client.reindex())
    elif sys.argv[1] == 'download':
        args = []
        kwargs = {}
        if sys.argv[2].startswith('magnet:'):
            mu = MagnetUri(sys.argv[2])
            kwargs = dict(outfile=mu.outfile, tth=mu.tth, size=mu.size)
        else:
            args = sys.argv[3:]
        pprint.pprint(client.download(*args, **kwargs))
    else:
        raise Exception('do not know what to do')
        
