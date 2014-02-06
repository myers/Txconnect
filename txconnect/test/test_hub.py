import pprint
from twisted.trial.unittest import TestCase
from twisted.test import proto_helpers
from twisted.python import components

import louie
from ..directconnect import hub, interfaces

class StubFileSource:
    size = 1024
        
class TestHubProtocol(TestCase):
    def setUp(self):
        app = components.Componentized()
        app.setComponent(interfaces.IFileSource, StubFileSource())
    
        self.proto = hub.HubClientProtocol(app)
        self.tr = proto_helpers.StringTransportWithDisconnection()
        self.tr.protocol = self.proto
        self.proto.makeConnection(self.tr)

    def tearDown(self):
        return self.tr.loseConnection()
    
    def _hubSends(self, data):
        self.proto.dataReceived(data)
   
    def assertClientSent(self, data):
        val = self.tr.value()
        self.assertEqual(data, val)
        self.tr.clear()
        
    def test_PtokaX_login(self):
        self.proto.hubId = '127.0.0.1:4242'
        self.proto.cred = dict(
          nick='foo', 
          password='bar', 
          connection='banana', 
          email='foo@bar.com',
        )
        
        self._hubSends('$Lock EXTENDEDPROTOCOL`<OtHAGQBBkLXDEfSqi1eK3E?9mwin Pk=PtokaX|')
        self.assertClientSent('$Supports UserCommand NoGetINFO NoHello QuickList ZPipe|')
        self._hubSends('$Supports QuickList|')
        self.assertClientSent('$MyINFO $ALL foo <txconnect V:1.0,M:A,H:0/1/0,S:10>$ $banana\x01$foo@bar.com$1024$|$GetNickList|')
        self._hubSends('$GetPass|')
        self.assertClientSent('$MyPass bar|')
        self._hubSends('$ZOn|x\x9cS\xf1(M\xf2K\xccMU\x08I-.Q\x00rj\x008\xac\x06@$MyINFO $ALL baz <++ V:1.0,M:A,H:0/1/0,S:10>$ $kiwi\x01$baz@evil.com$2048$|')
        self.assertEqual('Test Hub', self.proto.hubname)
        self.assertEqual('baz',  self.proto.peers.items()[0][0].nick)
                                        
    def test_viperpeers_login(self):
        self.proto.hubId = '127.0.0.1:4242'
        self.proto.cred = dict(
          nick='foo', 
          password='bar', 
          connection='banana', 
          email='foo@bar.com',
        )
        
        self._hubSends('$Lock EXTENDEDPROTOCOL_VIPERHUB Pk=versionHidden|')
        self.assertClientSent('$Key u\xd1\xc0\x11\xb0\xa0\x10\x10A \xd1\xb1\xb1\xc0\xc001\x90\xf1\x91Qq\xa1\xd1q|$ValidateNick foo|')
        self._hubSends('$HubName Test Hub|$Hello foo|')
        self.assertClientSent('$Version 1,0091|$GetNickList|$MyINFO $ALL foo <txconnect V:1.0,M:A,H:0/1/0,S:10>$ $banana\x01$foo@bar.com$1024$|')
        self._hubSends('$GetPass|')
        self.assertClientSent('$MyPass bar|')
        self.assertEqual('Test Hub', self.proto.hubname)
                                        
    def test_parseMyINFO(self):
        results = hub.parseMyINFO(u'<SP V:0.9.11,M:A,H:1/0/0,S:3>$ $DSL\x01$somebody@example.com$211716460$')
        
        self.assertEqual('SP', results['client'])
        self.assertEqual('0.9.11', results['clientVersion'])
        self.assertEqual(True, results['active'])
        self.assertEqual(1, results['hubsAsUser'])
        self.assertEqual(0, results['hubsAsOp'])
        self.assertEqual(0, results['hubsAsRegistered'])
        self.assertEqual(3, results['openSlots'])
        self.assertEqual('DSL', results['connectionType'])
        self.assertEqual('somebody@example.com', results['email'])
        self.assertEqual(211716460, results['shareSize'])

    def test_parseMyINFO_with_comment(self):
        results = hub.parseMyINFO(u'Ph33r t3h furry!<++ V:0.75,M:A,H:0/1/1,S:6>$ $20\x01$$33483370916$')
        
        self.assertEqual('++', results['client'])
        self.assertEqual('0.75', results['clientVersion'])
        self.assertEqual(True, results['active'])
        self.assertEqual(0, results['hubsAsUser'])
        self.assertEqual(1, results['hubsAsOp'])
        self.assertEqual(1, results['hubsAsRegistered'])
        self.assertEqual(6, results['openSlots'])
        self.assertEqual('20', results['connectionType'])
        self.assertEqual('', results['email'])
        self.assertEqual(33483370916, results['shareSize'])

    def test_parseMyINFO_other(self):
        hub.parseMyINFO(u'[4]danish comic book scanner<ApexDC++ V:s16.4,M:A,H:0/3/6,S:7>$ $2\t$ data9724@gmail.com$197154749330$')
        hub.parseMyINFO(u'<++ V:0.762,M:A,H:0/0/3,S:4,O:1>$ $0.005\x01$ComicHst@aol.com$29486067013$')

    def test_parseMyINFO_other2(self):
        results = hub.parseMyINFO(u'[14]$P$100\x05$$126737666190$')
        self.assertEqual({'connectionType': u'100', 'email': u'', 'shareSize': 126737666190}, results)
        
    def test_parseMyINFO_with_bad_data(self):
        self.assertRaises(hub.MyInfoParseError, hub.parseMyINFO, u'your mom')

    def test_handleTo(self):
        self.proto.hubId = '127.0.0.1:4242'
        message = u"<Kryten> The commands available to you are:\r\n\r\n(just type "
        def _(peer, sent_at, msg):
            louie.disconnect(_, 'hub:to')
            self.assertEqual(message, msg)
        louie.connect(_, 'hub:to')
        self._hubSends("$To: iamferret From: Kryten $%s|" % (message,))
