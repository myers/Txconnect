import re

def filesize(bytes):
    """
    >>> filesize(1025)
    '1 KiB'
    >>> filesize(10000000)
    '9.5 MiB'
    """
    bytes = float(bytes)

    if bytes == 0:
        return 0
    if bytes < 1024:
        return '<1 KiB'
    elif bytes < (1024 * 1024):
        return '%d KiB' % (bytes / 1024)
    elif bytes < (1024 * 1024 * 1024):
        return '%.1f MiB' % (bytes / 1024.0 / 1024.0)
    elif bytes < (1024 * 1024 * 1024 * 1024):
        return '%.1f GiB' % (bytes / 1024.0 / 1024.0 / 1024.0)
    else:
        return '%.1f TiB' % (bytes / 1024.0 / 1024.0 / 1024.0 / 1024.0)


def time(seconds, parts=2):
    """
    >>> time(10000000)
    '115d 17h'
    >>> time(10000)
    '2h 46m'
    """
    ret = []
    days = int(seconds / (60 * 60 * 24))
    seconds = seconds % (60 * 60 * 24)
    if days:
        ret.append('%dd' % (days,))
    hours = int(seconds / (60 * 60))
    seconds = seconds % (60 * 60)
    if ret or hours:
        ret.append('%dh' % (hours,))
    minutes = int(seconds / 60)
    seconds = seconds % 60
    if ret or minutes:
        ret.append('%dm' % (minutes,))
    ret.append('%ds' % (seconds,))
    return ' '.join(ret[:parts])

def number(num):
    """
    >>> number(12345)
    '12,345'
    >>> number(123456789)
    '123,456,789'
    """
    
    return (",".join(re.findall("\d{1,3}", str(num)[::-1])))[::-1]
        
        
if __name__ == "__main__":
    import doctest
    doctest.testmod()
                