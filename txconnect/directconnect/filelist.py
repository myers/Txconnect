import bz2, os, gc, ntpath, posixpath
from lxml import etree

def get_etree(filelist):
    return etree.parse(bz2.BZ2File(filelist))

# iterate over files in a directory in a file list.  this will be recursive.
# yields fullDcPath, relativeUnixPath, size, tth
def files(filelist, dirpath=None):
    root = get_etree(filelist)
    dirpathparts = []
    if dirpath:
        for part in dirpath.split('\\'):
            try:
                root = root.xpath('Directory[@Name="%s"]' % (part.replace('"', '&quot;'),))[0]
            except IndexError:
                raise NotFoundError('could not find part %r of path %r in filelist' % (part, dirpath,))
        dirpathparts = dirpath.split('\\')

    counter = 0
    for ee in list(root.getiterator())[1:]:
        if counter > 1000:
            gc.collect()
            counter = 0
        else:
            counter += 1
        
        if ee.tag != 'File':
            continue
        pathparts = [aa.get('Name') for aa in reversed(list(ee.iterancestors('Directory')))]
        dirpath = '\\'.join(pathparts)
        outpath = '/'.join(pathparts[len(dirpathparts):])
        yield dirpath + '\\' + ee.get('Name'), os.path.join(outpath, ee.get('Name')), int(ee.get('Size')), ee.get('TTH', None)


def files2(filelist):
    infile = bz2.BZ2File(filelist)
    context = etree.iterparse(infile, events=('end',), tag='File')
    dirpathparts = []
    for event, ee in context:
        pathparts = [aa.get('Name') for aa in reversed(list(ee.iterancestors('Directory')))]
        dirpath = '\\'.join(pathparts)
        outpath = '/'.join(pathparts[len(dirpathparts):])
        yield dirpath + '\\' + ee.get('Name'), os.path.join(outpath, ee.get('Name')), int(ee.get('Size')), ee.get('TTH', None)
        ee.clear()
        while ee.getprevious() is not None:
            del ee.getparent()[0]

class Directory(object):
    def __init__(self, path=None):
        self.path = path
        self.files = []
        self.dirs = []
    
    def child(self, name):
        if self.path is None:
            child = self.__class__(name)
        else:    
            child = self.__class__(ntpath.join(self.path, name))
        self.dirs.append(child)
        return child
    def basename(self):
        return ntpath.basename(self.path)
        
class File(object):
    def __init__(self, path, size, tth=None):
        self.path = path
        self.size = int(size)
        self.tth = tth
    def __repr__(self):
        return self.path
    def basename(self):
        return ntpath.basename(self.path)
    def unixpath(self):
        return posixpath.sep.join(self.path.split(ntpath.sep))
    def dirname(self):
        return ntpath.dirname(self.path)
        
def walk(filelist):
    try:
        infile = bz2.BZ2File(filelist)
        context = etree.iterparse(infile, events=('start', 'end',))
        directories = [Directory()]
        for event, ee in context:
            if ee.tag == 'Directory':
                if event == 'start':
                    directories.append(directories[-1].child(ee.get('Name')))
                elif event == 'end':
                    yield directories[-1].path, [dir.basename() for dir in directories[-1].dirs], directories[-1].files
                    directories.pop(-1)
            elif ee.tag == 'File' and event == 'end':
                directories[-1].files.append(File(ntpath.join(directories[-1].path, ee.get('Name')), ee.get('Size'), ee.get('TTH', None)))
    except etree.XMLSyntaxError:
        raise CorruptFilelistError(filelist)

class CorruptFilelistError(StandardError):
    pass
    
class NotFoundError(StandardError):
    pass
    