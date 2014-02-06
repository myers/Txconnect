import os, threading, Queue as queue, datetime, repr

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.python import log
from twisted.python.failure import Failure

from django.conf import settings
settings.configure(
  DATABASES = {
    'default': {
      'ENGINE': 'django.db.backends.sqlite3',
      'NAME': (os.environ.get('TXCONNECT_DATABASE_NAME', 'default.sqlite3')),
      'OPTIONS': {
        'timeout': 20,
      },
    },
    'trafficlog': {
      'ENGINE': 'django.db.backends.sqlite3',
      'NAME': (os.environ.get('TXCONNECT_TRAFFIC_LOG_DATABASE_NAME', 'trafficlog.sqlite3')),
      'OPTIONS': {
        'timeout': 20,
      },
    },
    'sharestore': {
      'ENGINE': 'django.db.backends.sqlite3',
      'NAME': (os.environ.get('TXCONNECT_SHARE_STORE_DATABASE_NAME', 'sharestore.sqlite3')),
      'OPTIONS': {
        'timeout': 40,
      },
    },
    'queuestore': {
      'ENGINE': 'django.db.backends.sqlite3',
      'NAME': (os.environ.get('TXCONNECT_QUEUE_STORE_DATABASE_NAME', 'queuestore.sqlite3')),
      'OPTIONS': {
        'timeout': 20,
      },
    },
  },
  DATABASE_ROUTERS = ['txconnect.app_db_router.AppDbRouter',],
  INSTALLED_APPS = ('txconnect.sharestore','txconnect.queuestore','txconnect.trafficlog', 'txconnect.webui',),
  DEBUG = True,
)
from django.db import reset_queries, close_connection, _rollback_on_exception, connections

THREAD_NAME = 'DjangoDB'

class Database(object):
    numberOfReadThreads = 5
    def __init__(self, name):
        self.started = threading.Event()

        self.writeQueue = queue.Queue(1000)
        self.writeThread = threading.Thread(target=self._dbThread, name=name, args=(self.writeQueue,))
        self.writeThread.setDaemon(True)
        self.writeThread.start()
        self.runWriteQuery(self.djangoSync)
        
        self.writeTrafficLogQueue = queue.Queue(1000)
        self.writeTrafficLogThread = threading.Thread(target=self._dbThread, name='%s trafficlog' % (name,), args=(self.writeTrafficLogQueue,))
        self.writeTrafficLogThread.setDaemon(True)
        self.writeTrafficLogThread.start()

        self.searchQueue = queue.Queue(1000)
        self.searchThread = threading.Thread(target=self._dbThread, name='%s search' % (name,), args=(self.searchQueue,))
        self.searchThread.setDaemon(True)
        self.searchThread.start()
        
        self.readQueue = queue.Queue(1000)
        self.readThreads = []
        for ii in range(self.numberOfReadThreads):
            tt = threading.Thread(target=self._dbThread, name='%s read %d' % (name, ii,), args=(self.readQueue,))
            tt.setDaemon(True)
            tt.start()
            self.readThreads.append(tt)
        self.started.wait()
        reactor.addSystemEventTrigger('after', 'shutdown', self.shutdown)

    #
    # Background execution thread
    #

    def djangoSync(self):
        from django.core.management import call_command
        try:
            call_command('syncdb', verbosity=0)
            for db_name in settings.DATABASES.keys():
                if db_name == 'default':
                    continue
                call_command('syncdb', database=db_name, verbosity=0)
        except Exception, ee:
            print ee
            raise
        self.started.set()
    
    def _dbThread(self, queue):
        while 1:
            op = queue.get()
            reset_queries()
            
            
            if op is None:
                close_connection()
                queue.task_done()
                return
            
            func, args, kwargs, d, finished = op
                
            start = datetime.datetime.now()
            try:
                result = d.callback, func(*args, **kwargs)
            except:
                _rollback_on_exception()
                result = d.errback, Failure()
            delta = datetime.datetime.now() - start
            queries = ''
            if delta.seconds > 0.5:
                q = []
                for conn in connections.all():
                    q.extend(conn.queries)
                queries = ': QUERIES: %r' % (q,)
                log.msg('Query took too long %s on thread %s queue %s: func =\n %r queries =\n %s' % (delta, threading.currentThread().getName(), queue.qsize(), repr.repr((func.__module__, func.func_name, args, kwargs,)), queries[:1024],))
            finished(*result)
            queue.task_done()

    #
    # Primary thread entry points
    #

    def runWriteQuery(self, func, *args, **kwargs):
        if self.writeQueue.qsize() > 100:
            log.msg('Whoa! The write queue is getting big (%d). What\'s going in this queue? %r %r %r' % (self.writeQueue.qsize(), func, args, kwargs,))
        result = Deferred()
        self.writeQueue.put_nowait((func, args, kwargs, result, reactor.callFromThread))
        return result

    def runTrafficLogWriteQuery(self, func, *args, **kwargs):
        if self.writeTrafficLogQueue.qsize() > 100:
            log.msg('Whoa! The traffic log write queue is getting big (%d). What\'s going in this queue? %r %r %r' % (self.writeTrafficLogQueue.qsize(), func, args, kwargs,))
        result = Deferred()
        self.writeTrafficLogQueue.put_nowait((func, args, kwargs, result, reactor.callFromThread))
        return result

    def runSearchQuery(self, func, *args, **kwargs):
        if self.searchQueue.qsize() > 100:
            log.msg('Whoa! The search queue is getting big (%d). What\'s going in this queue? %r %r %r' % (self.searchQueue.qsize(), func, args, kwargs,))
        result = Deferred()
        self.searchQueue.put_nowait((func, args, kwargs, result, reactor.callFromThread))
        return result

    def runReadQuery(self, func, *args, **kwargs):
        if self.readQueue.qsize() > 100:
            log.msg('Whoa! The read queue is getting big (%d). What\'s going in this queue? %r %r %r' % (self.readQueue.qsize(), func, args, kwargs,))
        result = Deferred()
        self.readQueue.put_nowait((func, args, kwargs, result, reactor.callFromThread))
        return result

    def blockingCallFromThread(self, func, *args, **kwargs):
        returnQueue = queue.Queue()
        dd = Deferred()
        def _finish(func, result):
            returnQueue.put(result)
        self.writeQueue.put((func, args, kwargs, dd, _finish))
        result = returnQueue.get()
        if isinstance(result, Failure):
           result.raiseException()
        return result    

    def blockingReadCallFromThread(self, func, *args, **kwargs):
        returnQueue = queue.Queue()
        dd = Deferred()
        def _finish(func, result):
            returnQueue.put(result)
        self.readQueue.put((func, args, kwargs, dd, _finish))
        result = returnQueue.get()
        if isinstance(result, Failure):
           result.raiseException()
        return result    

    def shutdown(self):
        log.msg('Read queue size %d, Write queue size %d' % (self.readQueue.qsize(), self.writeQueue.qsize(),))
        if self.writeThread.is_alive():
            self.writeQueue.put(None)
            log.msg('waiting for the write queue to empty')
            self.writeQueue.join()
            log.msg('join() write thread')
            self.writeThread.join()
        else:
            assert self.writeQueue.qsize() == 0
        
        if set([tt.is_alive() for tt in self.readThreads]) == set([True]):
            for tt in self.readThreads:
                self.readQueue.put(None)
            log.msg('waiting for the read queue to empty')
            self.readQueue.join()
            
            for tt in self.readThreads:
                log.msg('join() %r thread' % (tt.getName(),))
                tt.join()
        else:
            assert self.readQueue.qsize() == 0


global thread
global blockingCallFromThread
global blockingReadCallFromThread
global runWriteQuery
global runReadQuery

def setup():
    global thread
    global blockingCallFromThread
    global blockingReadCallFromThread
    global runOnDbThread
    global runWriteQuery
    global runReadQuery

    thread = Database(THREAD_NAME)
    runWriteQuery = thread.runWriteQuery
    runReadQuery = thread.runReadQuery
    blockingCallFromThread = thread.blockingCallFromThread
    blockingReadCallFromThread = thread.blockingReadCallFromThread

def writeQuery(function):
    global thread
    def _runOnDbThread(*args, **kwargs):
        if threading.currentThread() == thread.writeThread:
            return function(*args, **kwargs)
        return thread.runWriteQuery(function, *args, **kwargs)
    return _runOnDbThread

def writeTrafficLogQuery(function):
    global thread
    def _runOnDbThread(*args, **kwargs):
        if threading.currentThread() == thread.writeTrafficLogThread:
            return function(*args, **kwargs)
        return thread.runTrafficLogWriteQuery(function, *args, **kwargs)
    return _runOnDbThread

def searchQuery(function):
    global thread
    def _runOnDbThread(*args, **kwargs):
        if threading.currentThread() == thread.writeTrafficLogThread:
            return function(*args, **kwargs)
        return thread.runSearchQuery(function, *args, **kwargs)
    return _runOnDbThread

def readQuery(function):
    global thread
    def _runOnDbThread(*args, **kwargs):
        if threading.currentThread() in thread.readThreads:
            return function(*args, **kwargs)
        return thread.runReadQuery(function, *args, **kwargs)
    return _runOnDbThread
