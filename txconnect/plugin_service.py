import sys
from twisted.application import service
from twisted.python import log
from directconnect.interfaces import IConfig

class PluginService(service.MultiService):
    name = 'plugins'
    
    def __init__(self, application):
        service.MultiService.__init__(self)
        self.application = application
        #self.setServiceParent(application)
        
        #self.reload()

    @property
    def config(self):
        return IConfig(self.application)

    def startService(self):
        self.reload()
        service.MultiService.startService(self)      
        
    def reload(self):
        self.config.reload()
        

        if self.config.get('plugin_service', None) is None or self.config['plugin_service'].get('plugins', None) is None:
            return
        if self.config['plugin_service'].get('paths', None):
            for path in self.config['plugin_service']['paths']:
                if path not in sys.path:
                    sys.path.append(path)

        
        for plugin_name in self.config['plugin_service']['plugins']:
            log.msg('loading %r' % (plugin_name,)) 
            try:
                plugin_module = __import__(plugin_name)
                plugin_service = plugin_module.make_service(self.application)
                assert plugin_service.name == plugin_name
                plugin_service.setServiceParent(self)
                #self.application.addComponent(service, ignoreClass=1)
            except Exception, ee:
                log.msg('error while importing plugin %r: %r' % (plugin_name, ee,))
        
