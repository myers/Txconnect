import re

from twisted.trial.unittest import TestCase
from twisted.python import components
from twisted.test import proto_helpers

from ..directconnect import peer, interfaces

from mocker import Mocker, ANY

class TestHelper:
    def assertMatch(self, pattern, value):
        r = re.compile(pattern)
        self.assertNotEqual(None, r.match(value), "%r" % value)

    def send(self, line):
        self.proto.lineReceived(line)

class PeerAsDownloaderErrorTest(TestCase, TestHelper):
    def setUp(self):
        self.testPeer = peer.Peer('testuser', '127.0.0.1:1')
        app = components.Componentized()
        self.factory = peer.PeerServerFactory(app)
        self.proto = self.factory.buildProtocol(('127.0.0.1', 0))
        self.tr = proto_helpers.StringTransport()
        self.proto.makeConnection(self.tr)

    def tearDown(self):
        self.proto.setTimeout(None)
        return self.tr.loseConnection()

    def testRaiseUnexpectedConnectionError(self):
        def _():
            self.send('$MyNick testuser')
        self.assertRaises(peer.UnexpectedConnectionError, _)


class PeerAsDownloaderTest(TestCase, TestHelper):
    def setUp(self):
        self.testPeer = peer.Peer('testuser', '127.0.0.1:1')
        self.mocker = Mocker()
        app = components.Componentized()
        hubHerder = self.mocker.mock()
        app.setComponent(interfaces.IHubHerder, hubHerder)
        hub = self.mocker.mock()
        hub.cred
        self.mocker.result(dict(nick='code_under_test'))
        hubHerder.hubForPeer(self.testPeer)
        self.mocker.result(hub)
        
        peerHerder = self.mocker.mock()
        app.setComponent(interfaces.IPeerHerder, peerHerder)
        peerHerder.anyDownloadsNeededFromNick('testuser')
        self.mocker.result(True)
        peerHerder.registerConnection(ANY)
        
        self.factory = peer.PeerServerFactory(app)
        self.factory.listeningPort = self.mocker.mock() 
        self.factory.listeningPort.startListening()
        self.factory.listeningPort.stopListening()
        self.mocker.replay()
        
        self.proto = self.factory.buildProtocol(('127.0.0.1', 0))
        self.tr = proto_helpers.StringTransport()
        self.proto.makeConnection(self.tr)

    def tearDown(self):
        self.mocker.verify()
        
        self.proto.setTimeout(None)
        return self.tr.loseConnection()

    def doHandshake(self):
        self.factory.expectPeer(self.testPeer)
        self.assertEqual('handshaking', self.proto.status)
        self.send('$MyNick testuser')
        self.send('$Lock EXTENDEDPROTOCOLABCABCABCABCABCABC Pk=DCPLUSPLUS0.674ABCABC')
        self.assertMatch(r'\$MyNick code_under_test\|\$Lock EXTENDEDPROTOCOLABCABCABCABCABCABC Pk=TXCONNECT1.0ABCABCABC\|\$Supports XmlBZList ADCGet TTHF TTHL\|\$Direction Download (\d+)\|\$Key \x14\xd1\xc0\x11\xb0\xa0\x10\x10A \xd1\xb1\xb1\xc0\xc00\xd00\x10 0\x10 0\x10 0\x10 0\x10 0\x10\|', self.tr.value())
        self.tr.clear()
        self.send('$Supports MiniSlots XmlBZList ADCGet TTHL TTHF GetZBlock ZLIG ')
        self.send('$Direction Upload 6494')
        self.assertEqual('handshaking', self.proto.status)
        self.send('$Key \x14\xd1\xc0\x11\xb0\xa0\x10\x10A \xd1\xb1\xb1\xc0\xc00\xd00\x10 0\x10 0\x10 0\x10 0\x10 0\x10')
        self.assertEqual('idle', self.proto.status)

    def testHandshake(self):
        self.doHandshake()
    
    def testGetLeaves(self):
        leavesData = 'x' * 72
        self.doHandshake()
        dd = self.proto.getLeaves('LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI')
        def _(res):
            self.assertEqual(leavesData, res)
        dd.addCallback(_)
        
        self.assertEqual('$ADCGET tthl TTH/LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI 0 -1|', self.tr.value())
        self.tr.clear()

        self.send('$ADCSND tthl TTH/LWWBX5YTCGEBSA2ZS3KRHBNJTK7IOV3W6VGTLJI 0 72')
        self.proto.rawDataReceived(leavesData)
        self.assertEqual(True, dd.called)
        self.mocker.verify()
        
class PeerAsUploaderTest(TestCase, TestHelper):
    def setUp(self):
        locator = components.Componentized()

        self.tr = proto_helpers.StringTransport()
        self.proto = peer.PeerProtocol(application=locator, connecting=True)
        self.proto.makeConnection(self.tr)
        self.mocker = Mocker()
        self.proto.hub = self.mocker.mock()
        self.proto.hub.cred
        self.mocker.result(dict(nick='code_under_test'))
        self.proto.hub.peerForNick('testuser')
        self.mocker.result(peer.Peer('testuser', '127.0.0.1:1'))
        
        peerHerder = self.mocker.mock()
        locator.setComponent(interfaces.IPeerHerder, peerHerder)
        peerHerder.anyDownloadsNeededFromNick('testuser')
        self.mocker.result(False)
        #peerHerder.registerConnection(ANY)

        self.mocker.replay()


    def tearDown(self):
        self.mocker.verify()
        self.proto.setTimeout(None)
        return self.tr.loseConnection()

    def testHandshake(self):
        # the code is responding to some other peer's $ConnectToMe
        
        # PeerHerder sets this up in .connectToPeer()

        # we are peer 1 in http://www.teamfair.info/wiki/index.php?title=C_c_handshake
        # self.proto.hub set to a mock in the setup
        self.proto.startHandshake()
        self.assertEqual(r'$MyNick code_under_test|$Lock EXTENDEDPROTOCOLABCABCABCABCABCABC Pk=TXCONNECT1.0ABCABCABC|', self.tr.value())
        self.tr.clear()
        self.assertEqual('handshaking', self.proto.status)
        self.send('$MyNick testuser')
        self.send('$Lock EXTENDEDPROTOCOLABCABCABCABCABCABC Pk=DCPLUSPLUS0.668ABCABC')
        self.send('$Supports XmlBZList ADCGet')
        self.send('$Direction Download 17762')
        self.send('$Key \x14\xd1\xc0\x11\xb0\xa0\x10\x10A \xd1\xb1\xb1\xc0\xc00\xd00\x10 0\x10 0\x10 0\x10 0\x10 0\x10')
        self.assertMatch(r'\$Supports XmlBZList ADCGet TTHF TTHL\|\$Direction Upload (\d+)\|\$Key \x14\xd1\xc0\x11\xb0\xa0\x10\x10A \xd1\xb1\xb1\xc0\xc00\xd00\x10 0\x10 0\x10 0\x10 0\x10 0\x10\|', self.tr.value())
        self.tr.clear()
        self.assertEqual('idle', self.proto.status)

class PeerTest(TestCase, TestHelper):
      def testOnlyOneObject(self):
          pp1 = peer.Peer('foo', 'bar.com')
          pp2 = peer.Peer('foo', 'bar.com')
          self.assertEqual(id(pp1), id(pp2))

      def testStringInit(self):
          pp1 = peer.Peer('foo$bar.com')
          pp2 = peer.Peer('foo', 'bar.com')
          self.assertEqual(id(pp1), id(pp2))

      def testToStr(self):
          self.assertEqual('foo$bar.com', str(peer.Peer('foo', 'bar.com')))

      def testRaisesErrorIfGivenTuple(self):
          def _():
              peer.Peer('foo', ('bar.com', 411))
          self.assertRaises(Exception, _)

                                