import datetime

from django.db import models

class LogEntry(models.Model):
    def __unicode__(self):
        return '%r with %r for %r' % (self.type, self.peer, self.path,)
        
    TYPE_CHOICES = (
      (u'U', u'upload'),
      (u'D', u'download'),
    )
                    
    type = models.CharField(max_length=1, choices=TYPE_CHOICES)
    peer = models.CharField(db_index=True, max_length=255)
    path = models.TextField(db_index=True)
    tth = models.CharField(max_length=39, null=True, db_index=True)
    priority = models.PositiveIntegerField(default=0, db_index=True)

    offset = models.PositiveIntegerField(default=0)
    requested_length = models.PositiveIntegerField(default=0)
    actual_length = models.PositiveIntegerField(default=0)

    start = models.DateTimeField(editable=False, default=datetime.datetime.now, db_index=True)
    end = models.DateTimeField(editable=False, null=True, db_index=True)

    class Meta:
        ordering = ['start']

