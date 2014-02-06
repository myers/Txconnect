import itertools, heapq

class PriorityQueue(object):
    INVALID = 0                     # mark an entry as deleted
    def __init__(self):
        self.pq = []                         # the priority queue list
        self.counter = itertools.count(1)    # unique sequence count
        self.task_finder = {}                # mapping of tasks to entries

    def __len__(self):
        return len(self.pq)
        
    def addTask(self, priority, task, count=None):
        assert type(priority) is int
        priority = priority * -1
        if count is None:
            count = self.counter.next()
        entry = [priority, count, task]
        self.task_finder[task] = entry
        heapq.heappush(self.pq, entry)
        return self.pq.index(entry)

    def getTopPriority(self):
        while True:
            try:
                priority, count, task = heapq.heappop(self.pq)
            except IndexError:
                return
            del self.task_finder[task]
            if count is not self.INVALID:
                return task

    def deleteTask(self, task):
        entry = self.task_finder[task]
        entry[1] = self.INVALID

    def reprioritize(self, priority, task):
        entry = self.task_finder[task]
        self.addTask(priority, task, entry[1])
        entry[1] = self.INVALID
