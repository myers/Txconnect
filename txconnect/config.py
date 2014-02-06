from directconnect.interfaces import IConfig
from twisted.python.filepath import FilePath
from zope.interface import implements
import yaml

from UserDict import DictMixin

class Config(DictMixin):
    implements(IConfig)

    def __init__(self, dataDir):
        self.dataDir = dataDir
        self.configFile = self.dataDir.child('config.yml')
        self.config = None
        if not self.configFile.exists():
            FilePath(__file__).sibling('config.yml.sample').copyTo(self.configFile)
        self.reload()

    def reload(self):
        self.config = yaml.load(self.configFile.open('r'))

    def __getitem__(self, key):
        return self.config.__getitem__(key)

    def keys(self):
        return self.config.keys()
