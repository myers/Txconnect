import os

from zope.interface import implements

from twisted.python import usage, components
from twisted.python.filepath import FilePath
from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker
from twisted.application import service

class Options(usage.Options):
    optParameters = [['data', 'd', '~/.txconnect', 'The data directory to use.  Defaults to ~/.txconnect/.']]

class TxconnectServiceMaker(object):
    implements(IServiceMaker, IPlugin)
    tapname = 'txconnect'
    description = 'A DirectConnect client.'
    options = Options

    def makeService(self, options):
        dataDir = FilePath(os.path.expanduser(options['data']))
        if not dataDir.isdir():
            dataDir.makedirs()

        os.environ['TXCONNECT_DATABASE_NAME'] = dataDir.child('dj.sqlite3').path
        os.environ['TXCONNECT_TRAFFICLOG_DATABASE_NAME'] = dataDir.child('trafficlog.sqlite3').path
        from txconnect import dbthread
        dbthread.setup()

        # have to import these after dbthread is setup
        from txconnect.directconnect import search, hub_herder, peer_herder, interfaces
        from txconnect import plugin_service, queuestore, sharestore, memory, web_service, config
        from txconnect import downloader_manager, trafficlog, extutils
        
        locator = components.ReprableComponentized()
        txconnectService = service.MultiService()
        txconnectService.name = 'txconnect'
        locator.setComponent(service.IServiceCollection, txconnectService)
        
        configObj = config.Config(dataDir)
        locator.setComponent(interfaces.IConfig, configObj)

        memoryService = memory.MemoryService(locator)
        memoryService.setServiceParent(txconnectService)
        locator.setComponent(interfaces.IMessageMemory, memoryService)

        downloadQueue = queuestore.QueueStore(locator)
        locator.setComponent(interfaces.IDownloadQueue, downloadQueue)

        downloaderManager = downloader_manager.DownloaderManager(locator)
        downloaderManager.setServiceParent(txconnectService)
        locator.setComponent(interfaces.IDownloaderManager, downloaderManager)

        fileSource = sharestore.ShareStore(locator)
        fileSource.setServiceParent(txconnectService)
        locator.setComponent(interfaces.IFileSource, fileSource)

        searchHerder = search.SearchHerder(locator)
        searchHerder.setServiceParent(txconnectService)
        locator.setComponent(interfaces.ISearchHerder, searchHerder)

        hubHerder = hub_herder.HubHerder(locator)
        hubHerder.setServiceParent(txconnectService)
        locator.setComponent(interfaces.IHubHerder, hubHerder)

        peerHerder = peer_herder.PeerHerder(locator)
        peerHerder.setServiceParent(txconnectService)
        locator.setComponent(interfaces.IPeerHerder, peerHerder)

        trafficLogger = trafficlog.TrafficLogger(locator)
        trafficLogger.setServiceParent(txconnectService)

        webService = web_service.make_service(locator)
        webService.setServiceParent(txconnectService)

        extUtils = extutils.ExtUtilsService()
        extUtils.setServiceParent(txconnectService)
        locator.setComponent(interfaces.IHasher, extUtils)
        locator.setComponent(interfaces.IDirLister, extUtils)

        if configObj.has_key('manhole') and configObj['manhole'].has_key('port'):
            from twisted.conch import manhole_tap
            manholeService = manhole_tap.makeService({
              'telnetPort': str(configObj['manhole']['port']), 
              'namespace': {'locator': locator}, 
              'passwd': 'passwd',
              'sshPort': None,
            })
            manholeService.setName('manhole')
            manholeService.setServiceParent(txconnectService)

        plugins = plugin_service.PluginService(locator)
        plugins.setServiceParent(txconnectService)
        
        return txconnectService

# Now construct an object which *provides* the relevant interfaces
# The name of this variable is irrelevant, as long as there is *some*
# name bound to a provider of IPlugin and IServiceMaker.

serviceMaker = TxconnectServiceMaker()
