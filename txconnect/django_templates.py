from twisted.python.filepath import FilePath
from django.conf import settings

settings.TEMPLATE_DIRS = (FilePath(__file__).parent().child('webui').child('templates').path,)

import django.template
import django.template.loader

def render(name, *values):
    ctx = django.template.Context()
    for d in values:
        ctx.push()
        ctx.update(d)

    t = django.template.loader.get_template(name)
    return str(t.render(ctx).encode('utf-8'))

def render_string(template, *values):
    ctx = django.template.Context()
    for d in values:
        ctx.push()
        ctx.update(d)

    t = django.template.loader.get_template_from_string(template)
    return str(t.render(ctx).encode('utf-8'))
