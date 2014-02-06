import os, datetime

from twisted.python.filepath import FilePath

from django.db import models
from ..base64_field import Base64Field

class Label(models.Model):
    label = models.CharField(db_index=True, max_length=255)
    
    def __unicode__(self):
        return self.label

class FileManager(models.Manager):
    def size_by_priority(self):
        return self.values('priority').annotate(size=models.Sum('size'), count=models.Count('id'))
    
    def with_label(self, label):
        return self.filter(label__label=label)

class File(models.Model):
    objects = FileManager()
    
    def __unicode__(self):
        return self.outpath
        
    TYPE_CHOICES = (
      (u'F', u'file'),
      (u'L', u'filelist'),
      (u'D', u'directory'),
    )
                    
    directory = models.TextField(db_index=True)
    name = models.TextField()
    type = models.CharField(max_length=1, choices=TYPE_CHOICES)
    tth = models.CharField(max_length=39, unique=True, null=True)
    size = models.IntegerField(null=True)
    leaves = Base64Field(null=True)
    priority = models.PositiveIntegerField(default=0)
    
    created = models.DateTimeField(editable=False, default=datetime.datetime.now)
    last_searched_for_sources = models.DateTimeField(editable=False, default=datetime.datetime.now, db_index=True)
    
    label = models.ForeignKey(Label, null=True)

    class Meta:
        unique_together = ('directory', 'name')
        ordering = ['name']

    @property
    def outpath(self):
        return os.path.join(self.directory, self.name)
        
    @property
    def filepath(self):
        return FilePath(self.outpath)
    
    @property
    def canMultisource(self):
        return bool(self.tth)

class Source(models.Model):
    def __unicode__(self):
        return "%s is a source for %r" % (self.peer, self.file)
        
    file = models.ForeignKey(File)

    peer = models.CharField(db_index=True, max_length=255)
    
    dcPath = models.TextField()

"""
class Peer(models.Model):
    def __unicode__(self):
        return "%s is a source for %r" % (self.peer, self.file)
        
    nick = models.CharField(db_index=True, max_length=255
    hub = models.CharField(db_index=True, max_length=255)
    
    timeouts = models.PostiveIntegerField()
    
    # bytes per second
    average_rate = models.PostiveIntegerField()
"""        