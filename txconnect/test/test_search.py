from twisted.trial.unittest import TestCase
from twisted.python import components

from ..directconnect import search, interfaces

class Stub:
    pass

class StubProtocol:
    def __init__(self):
        self.sending = []
    def send(self, results, dest):
        self.sending.append((results, dest,))
    
class TestSearch(TestCase):
    def testRespondToSearch(self):
        """
        test a fix for a bug that looked like this:
        
        File "/other/p/txconnect/directconnect/client.py", line 210, in respondToSearch
         seachResults.append("$SR %s %s\x05%s %d/%d\x05TTH:%s (%s:%s)" % (hub.cred["nick"], ii[0].encode(DC_ENCODING), ii[1], self.unusedSlots, self.maxSlots, ii[2], hub.hubAddr[0], hub.hubAddr[1],))
         exceptions.UnicodeDecodeError: 'utf8' codec can't decode byte 0xae in position 30: unexpected code byte
        """
        hubStub = Stub()
        hubStub.nick = 'foo'
        hubStub.hubAddr = ('127.0.0.1', 4000,)
        peerHerder = Stub()
        peerHerder.maxSlots = 10
        peerHerder.unusedSlots = 1
        app = components.Componentized()
        app.setComponent(interfaces.IPeerHerder, peerHerder)
        sh = search.SearchHerder(app)
        sh.ip = '127.0.0.1'
        sh.port = 4000
        sh.searchResponseProtocol = StubProtocol()

        results = [(u'\xaerourke\\monkey.txt', 21347259, u'BGPHT4KOEDJCIFYFNEKII6OTZVFPKUTJPLZVEUQ',)]

        sh._respondToSearch('127.0.0.2:21112', hubStub, results)
        
        self.assertEqual(str, type(sh.searchResponseProtocol.sending[0][0]))
        

class ParseSearchResultsTest(TestCase):
    def test_parseSearchResults1(self):
        result = 'iamferret stuff-for-cg\\terminology.txt\x051313 8/8\x05TTH:6WHLIXNAURBQE5JSKMCAQXECSSWR2LSINB7SYFQ (192.168.42.5:5000)'
        parsed = search.parseSearchResults(result)
        self.assertEqual({'hubname': None, 'filepath': u'stuff-for-cg\\terminology.txt', 'nick': u'iamferret', 'tth': '6WHLIXNAURBQE5JSKMCAQXECSSWR2LSINB7SYFQ', 'slots': (8, 8), 'size': 1313, 'type': 'file', 'hubaddr': ('192.168.42.5', 5000)}, parsed)

    def test_parseSearchResults2(self):
        result = 'localczdc Downloads\\Astro City 1/1\x05Open DC Hub (192.68.51.5:5642)'
        parsed = search.parseSearchResults(result)
        self.assertEqual({'hubname': 'Open DC Hub', 'filepath': 'Downloads\\Astro City', 'nick': u'localczdc', 'tth': None, 'slots': (1, 1), 'type': 'directory', 'hubaddr': ('192.68.51.5', 5642)}, parsed)
        