from twisted.internet import defer
from twisted.trial.unittest import TestCase
from twisted.python import components

from ..directconnect import hub_herder, interfaces

class HubHerderTest(TestCase):
    def testFirst(self):
        app = components.Componentized()
        config = dict(hubs=[])
        app.setComponent(interfaces.IConfig, config)

        class FakeFileSource:
            def __init__(self):
                self.setupDone = defer.succeed(True)
        app.setComponent(interfaces.IFileSource, FakeFileSource())

        hh = hub_herder.HubHerder(app)
        hh.startService()

