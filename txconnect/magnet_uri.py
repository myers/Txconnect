import cgi

# magnet:?xt=urn:tree:tiger:AB6FVD2JZEB4GFZ5I5YXOMO4ILLDHLIHXN6CQCI&xl=15115799&dn=01%20-%20Mother%20of%20All%20Funk%20Chords.mp4
class MagnetUri:
    def __init__(self, uri):
        self.uri = uri
        
        self.parsed = cgi.parse_qs(uri.replace('magnet:?', ''))

    @property
    def tth(self):
        assert self.parsed.has_key('xt')
        assert 'urn:tree:tiger:' in self.parsed['xt'][0] 
        return self.parsed['xt'][0].replace('urn:tree:tiger:', '')
    
    @property
    def size(self):
        assert self.parsed.has_key('xl')
        assert self.parsed['xl'][0].isdigit()
        return int(self.parsed['xl'][0])
    
    @property
    def outfile(self):
        assert self.parsed.has_key('dn')
        return self.parsed['dn'][0]
