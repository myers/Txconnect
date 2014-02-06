import sys, os, pickle, struct, signal

class Worker(object):
    prefix = '!I'
    prefixSize = struct.calcsize(prefix)

    def __init__(self, debug=True):
        self.debug = debug
        self.methods = {'quit': self.quit}

        if self.debug:
            self._log = file("%s.log" % (os.getpid(),), 'a')
            self.log('start up')
        
    def quit(self):
        self.send_results(True)
        self.log('quiting as requested')
        sys.exit(0)
        
    def log(self, msg):
        if self.debug:
            self._log.write(msg + '\n')
            self._log.flush()
    
    def addMethod(self, func, name=None):
        if name is None:
            name = func.func_name
        self.methods[name] = func
        
    def sigint_handler(self, *args):
        pass
        
    def run(self):
        signal.signal(signal.SIGINT, self.sigint_handler)
        signal.siginterrupt(signal.SIGINT, False)
        while True:
            size = struct.unpack(self.prefix, sys.stdin.read(self.prefixSize))[0]
            self.log('now reading %s bytes' % (size,))
            payload = sys.stdin.read(size)
            cmd = pickle.loads(payload)
            self.log("got %r" % (cmd,))
            if self.methods.has_key(cmd['method']):
                method = self.methods[cmd['method']]
                try:
                    self.send_results(method(*cmd['args']))
                except Exception, ee:
                    self.send_results(ee, exception=True)

    def send_results(self, result, exception=False):
        self.log("send %r" % (result,))
        if exception:
            payload = dict(exception=result)
        else:
            payload = dict(result=result)
        payload = pickle.dumps(payload, pickle.HIGHEST_PROTOCOL)
        sys.stdout.write(struct.pack('!I', len(payload)) + payload)
        sys.stdout.flush()
        
