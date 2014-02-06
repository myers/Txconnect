class AppDbRouter(object):
    """A router to control all database operations on models in
    the trafficlog application"""

    APP_WITH_THEIR_OWN_DBS = ('trafficlog', 'queuestore', 'sharestore',)

    def db_for_read(self, model, **hints):
        "Point all operations on trafficlog models to 'trafficlog'"
        if model._meta.app_label in self.APP_WITH_THEIR_OWN_DBS:
            return model._meta.app_label
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label in self.APP_WITH_THEIR_OWN_DBS:
            return model._meta.app_label
        return None

    def allow_relation(self, obj1, obj2, **hints):
        for name in self.APP_WITH_THEIR_OWN_DBS:
            if obj1._meta.app_label == name and obj2._meta.app_label == name:
                return True
        return None

    def allow_syncdb(self, db, model):
        "Make sure the trafficlog app only appears on the 'trafficlog' db"
        for name in self.APP_WITH_THEIR_OWN_DBS:
            if db == name:
                return model._meta.app_label == name
        return None
