import re

from twisted.trial.unittest import TestCase
from twisted.python import components
from twisted.test import proto_helpers

from ..directconnect import peer_herder, peer, interfaces, errors

from mocker import Mocker, ANY
import fudge

class PeerHerderTest(TestCase):
    def setUp(self):
    
        
        self.testPeer = peer.Peer('testuser', '127.0.0.1:1')
        self.mocker = Mocker()
        locator = components.Componentized()

        config = {'networking': {'port': 6666}, 'files': {}}
        locator.setComponent(interfaces.IConfig, config)

        hubHerder = self.mocker.mock()
        locator.setComponent(interfaces.IHubHerder, hubHerder)
        hubHerder.hubForPeer(self.testPeer)
        hub = self.mocker.mock()
        self.mocker.result(hub)

        hub.peers
        self.mocker.result({self.testPeer: {}})
        
        hub.activeMode
        self.mocker.result(True)
        
        hub.connectToMe(self.testPeer)
        
        self.mocker.replay()
        
        self.peerHerder = peer_herder.PeerHerder(locator)        
        self.peerHerder.startService()

    def tearDown(self):
        self.mocker.verify()
        
        return self.peerHerder.stopService()

    def testTakeAPeer(self):
        def _callback(connection):
            pass
        self.peerHerder.takeAPeer(self.testPeer, _callback)

class PeerHerderSlotTest(TestCase):
    def setUp(self):
        self.testPeer = peer.Peer('testuser', '127.0.0.1:1')
        locator = components.Componentized()

        config = {'networking': {'port': 6666}, 'files': {}}
        locator.setComponent(interfaces.IConfig, config)
        self.peerHerder = peer_herder.PeerHerder(locator)        
        self.peerHerder.startService()

    def testSlots(self):
        self.peerHerder.takeASlot(self.testPeer)
        self.assertEqual(1, self.peerHerder.usedSlots)

    def testUploadGetsQueued(self):
        for i in range(1,9):
            self.peerHerder.takeASlot(peer.Peer('test_%d' % (i,), 'testhub'))
        self.assertEqual(8, self.peerHerder.usedSlots)
        
        ee = self.assertRaises(errors.MaxedOutError, self.peerHerder.takeASlot, peer.Peer('test_9', 'testhub'))
        self.assertEqual(1, ee.args[0])

        self.assertEqual(1, len(self.peerHerder._uploadQueue))
        
        self.peerHerder.releaseASlot(peer.Peer('test_1', 'testhub'))
        self.assertEqual(7, self.peerHerder.usedSlots)
        self.assertEqual(1, len(self.peerHerder._uploadQueue))
        self.peerHerder.takeASlot(peer.Peer('test_9', 'testhub'))
        self.assertEqual(0, len(self.peerHerder._uploadQueue))
        self.assertEqual(8, self.peerHerder.usedSlots)
        