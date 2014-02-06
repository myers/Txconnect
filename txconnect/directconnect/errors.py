class MaxedOutError(StandardError):
    pass

class FileNotAvailableError(StandardError):
    pass

class PeerNoLongerConnectedError(StandardError):
    pass

class NotConnectedToHubError(StandardError):
    pass

class TimeoutError(StandardError):
    pass

class ParseError(StandardError):
    pass
            
class PeerNotFound(StandardError):
    pass
