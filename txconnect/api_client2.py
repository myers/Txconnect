import jsonrpc
from jsonrpc.proxy import JSONRPCProxy

class ApiClient(JSONRPCProxy):
    def __init__(self, settings):
        JSONRPCProxy.__init__(self, 