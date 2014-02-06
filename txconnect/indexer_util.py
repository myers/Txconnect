import os, time
from workerpool.worker import Worker
import tth
        
w = Worker(debug=True)

@w.addMethod
def tth_file(filepath):
    start = time.time()
    tthobj = tth.TTH(filepath)
    elapsed = time.time() - start
    return tthobj.getroot(), tthobj.getleaves(), elapsed

@w.addMethod
def list_dir(path):
    if isinstance(path, unicode):
        path = path.encode('utf-8')
    entries = []
    for fn in os.listdir(path):
        entry = dict(name=fn, type='f')
        fp = os.path.join(path, fn)

        # ignore broken symlinks
        if not os.path.exists(fp):
            continue

        if os.path.isdir(fp):
            entry['type'] = 'd'
        else:
            entry['size'] = os.path.getsize(fp)
            entry['mtime'] = os.path.getmtime(fp)
        entries.append(entry)
    return entries
    
if __name__ == '__main__':
    w.run()
