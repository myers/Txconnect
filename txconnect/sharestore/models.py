import os, ntpath, datetime, collections, operator

from twisted.python.filepath import FilePath, UnlistableError

from django.db import models
from django.db.utils import DatabaseError
from django.db.models import Q

from .. import base64_field
"""
This is denormalized for the sake of speed:

to search for a single keyword limited to 10 results
  Normalized (with a table for roots, directories, files and tth): 9s 
  Denormalized: 0.5 
  
doing a search for two keywords would be worse
"""

class PathManager(models.Manager):
    def size_and_count(self):
        size, count = self.aggregate(models.Sum('size'), models.Count('id')).values()
        if size == None:
            size = 0
        return size, count
    
    def delete_not_in_roots(self):
        for path in self.filter(directory=None).exclude(path__in=Path.roots.keys()):
            self._delete_dir(path)

    # hack because sqlite freaks out when you try to delete a deep tree (more than 999 arguments)
    def _delete_dir(self, path):
        if path.filetype == 8:
            for child in path.file_set.exclude(filetype=8):
                child.delete()
        for pp in self.filter(directory=path, filetype=8):
            self._delete_dir(pp)
        try:
            path.delete()
        except:
            print path
            raise
        
    def indexed_directories(self):
        ret = collections.OrderedDict()
        for directory in self.filter(filetype=8).order_by('-path'):
            try:
                ret[directory.filepath] = directory
            except KeyError:
                pass
        return ret

    def delete_paths(self, paths):
        ids = [path.id for path in paths.values()]
        list_size = 50
        for subset_of_ids in [ids[i:i+list_size] for i in xrange(0, len(ids), list_size)]:
            try:	
                self.filter(pk__in=subset_of_ids).delete()
            except DatabaseError:
                print "%r" % (subset_of_ids,)
                raise

    def search(self, term, maxsize=None, minsize=None, filetype=1, filter=None):
        qs = self.all()

        terms = term.replace('"', '').split()
        search_term = ' AND '.join([tt + '*' for tt in terms])
        qs = qs.extra(where=['sharestore_path_fts.path MATCH "%s" AND sharestore_path_fts.id = sharestore_path.id' % (search_term,)], tables=["sharestore_path_fts"])
        if filter:
            # this would work with all backends, but sqlite can do this faster 
            #qs = qs.filter(reduce(operator.__or__([Q(path_startswith=ff+'\\') for ff in filter])))
            qs = qs.filter(reduce(operator.__or__, (Q(path__gte=ff+'\\', path__lt=ff+']') for ff in filter)))
        if maxsize:
            qs = qs.filter(size__lte=maxsize)
        elif minsize:
            qs = qs.filter(size__gte=minsize)
        if filetype != 1:
            qs = qs.filter(filetype=filetype)
        res = []
        for ii in qs[:10]:
            res.append( (ii.path, ii.size, ii.tth,) )
        return res

    def search_tth(self, tth, filter=None):
        qs = self.filter(tth=tth[4:])
        if filter:
            qs = qs.filter(reduce(operator.__or__, (Q(path__gte=ff+'\\', path__lt=ff+']') for ff in filter)))
        return [(ii.path, ii.size, ii.tth) for ii in qs[:10]]

            
class Path(models.Model):
    roots = {}

    objects = PathManager()

    path = models.TextField(unique=True)

    TYPE_CHOICES = (
      (1, u'Unknown'),
      (2, u'Audio'),
      (3, u'Compressed'),
      (4, u'Document'),
      (5, u'Executable'),
      (6, u'Picture'),
      (7, u'Video'),
      (8, u'Directory'),
    )
    filetype = models.PositiveIntegerField(max_length=1, choices=TYPE_CHOICES, db_index=True)

    size = models.PositiveIntegerField(null=True, db_index=True)
    tth = models.CharField(max_length=39, null=True, db_index=True)
    mtime = models.DateTimeField(null=True)
    directory = models.ForeignKey('self', null=True, related_name='file_set', db_index=True, on_delete=models.CASCADE)

    def __unicode__(self):
	return self.path
    
    @property
    def basename(self):
        return ntpath.basename(self.path)
        
    @property
    def pathname(self):
        pathParts = self.path.split(ntpath.sep)
        root = self.roots[pathParts[0]].path
        return os.path.join(root, *pathParts[1:])

    @property
    def filepath(self):
        if not hasattr(self, '_filepath'):
            self._filepath = FilePath(self.pathname)
        return self._filepath

    def current_mtime(self):
        return datetime.datetime.fromtimestamp(self.filepath.getModificationTime())
      
    def up_to_date(self, current_mtime=None):
        if not self.filepath.exists():
            return False
        if self.mtime is None:
            return False
        if current_mtime is None:
            current_mtime = self.current_mtime()
        else:
            current_mtime = datetime.datetime.fromtimestamp(current_mtime)
        delta = current_mtime - self.mtime
        if delta > datetime.timedelta(microseconds=2):
            return False
        if self.filetype != 8 and self.size != self.filepath.getsize():	
            return False
        return True
       
    @property
    def is_dir(self):
        return self.filetype == 8
         
    # mtime is null for directories until we are done hashing all the files in them
    def mark_up_to_date(self, save=False, filelist=None):
        if self.is_dir:
            if filelist is None:
                file_count = self.count_files()
            else:
                file_count = len(filelist)
            if self.file_set.count() != file_count:
                return
        self.mtime = self.current_mtime()
        if not self.is_dir:
            self.size = self.filepath.getsize()
            
        if save:
            self.save()

    def count_files(self):
        assert self.is_dir
        children = [cc for cc in self.filepath.children() if shouldIndexFilepath(cc) and not cc.isdir()]
        return len(children)

    def save(self, *args, **kwargs):
        if not self.is_dir:
            self.mark_up_to_date()
            
        if not self.is_dir:
            assert self.mtime
        
        return super(Path, self).save(*args, **kwargs)

    def passes_filter(self, filter):
        for ff in filter:
            if self.path.startswith(ff):
                return True
        return False
        
class HashLeaves(models.Model):
    tth = models.CharField(max_length=39, primary_key=True)
    leaves = base64_field.Base64Field()

    def __unicode__(self):
        return 'leaves for %r' % (self.tth,)

def shouldIndexFilepath(filepath):
    if not (filepath.isfile() or filepath.isdir()):
        return False
    if filepath.basename().startswith('.'):
        return False
    return True 
