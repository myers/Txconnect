from django import template

register = template.Library()
def escape_hash(value):
    return value.replace('#', '%23')
register.filter('escape_hash', escape_hash)


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter(name='sort')
def listsort(value):
    if isinstance(value, dict):
        new_dict = SortedDict()
        key_list = value.keys()
        key_list.sort()
        for key in key_list:
            new_dict[key] = value[key]
        return new_dict
    elif isinstance(value, list):
        new_list = list(value)
        new_list.sort()
        return new_list
    else:
        return value
listsort.is_safe = True    

@register.filter(name='attrsort')
def attrsort(value, attrname):
    new_list = list(value)
    new_list.sort(key=lambda xx: getattr(xx, attrname))
    return new_list
attrsort.is_safe = True    
