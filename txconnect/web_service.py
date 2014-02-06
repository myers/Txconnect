import os

from zope.interface import implements

from twisted.application import internet
from twisted.web import script, static
from twisted.cred.portal import IRealm, Portal
from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse
from twisted.web.resource import IResource
from twisted.web.guard import HTTPAuthSessionWrapper, DigestCredentialFactory, BasicCredentialFactory

import wsapi, websocket
from directconnect.interfaces import IConfig

def make_service(application):
    config = IConfig(application)

    webRoot = static.File(os.path.join(os.path.dirname(__file__), 'webui'))
    def rpyProcessor(path, registry):
       rsc = script.ResourceScript(path, registry)
       rsc.application = application
       return rsc
    webRoot.processors = {'.rpy': rpyProcessor}
    webRoot.ignoreExt('.rpy')
    class WebUIRealm(object):
        implements(IRealm)

        def requestAvatar(self, avatarId, mind, *interfaces):
            if IResource in interfaces:
                return (IResource, webRoot, lambda: None)
            raise NotImplementedError()

    checker = InMemoryUsernamePasswordDatabaseDontUse()
    checker.addUser(config['webui']['username'], config['webui']['password'])
    portal = Portal(WebUIRealm(), [checker])

    #credentialFactory = DigestCredentialFactory('MD5', 'txconnect')
    #credentialFactory.CHALLENGE_LIFETIME_SECS = 1500 * 60
    credentialFactory = BasicCredentialFactory('txconnect')
    
    authRoot = HTTPAuthSessionWrapper(portal, [credentialFactory])

    site = websocket.WebSocketSite(authRoot)
    site.addHandler('/wsapi', wsapi.WebUIHandler)
    site.application = application
    
    if 'http_port' in config['webui']:
        web = internet.TCPServer(config['webui']['http_port'], site)
    if 'https_port' in config['webui']:
        from twisted.internet import ssl
        sslContext = ssl.DefaultOpenSSLContextFactory(
          config['webui']['ssl']['key'], 
          config['webui']['ssl']['cert'],
        )
        web = internet.SSLServer(config['webui']['https_port'], site, contextFactory = sslContext)
    web.setName('webui')
    return web
