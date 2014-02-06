import re

def lockToKey(lock):
    # http://dc.selwerd.nl/doc/Appendix_A.html
    try:
        lock, pk = lock.split(" ")[:2]
    except:
        print lock
        raise
    key = [None] * len(lock)
    for ii in xrange(1, len(lock)):
        key[ii] = ord(lock[ii]) ^ ord(lock[ii-1])
    key[0] = ord(lock[0]) ^ ord(lock[-1]) ^ ord(lock[-2]) ^ 5
    for ii in xrange(len(lock)):
        key[ii] = ((key[ii]<<4) & 240) | ((key[ii]>>4) & 15)
    
    def quote(char):
        if char in (0, 5, 36, 96, 124, 126,):
            return "/%%DCN%03d%%/" % (char,)
        return chr(char)
    key = map(quote, key)
    return ''.join(key)

def parseCommand(line, client=False):
    if line == "":
        cmd, data =  None, None
    elif line[0] == "$" and not line.count(" "):
        cmd, data = line[1:], None
    elif line[0] == "$":
        cmd, data = line[1:].split(" ", 1)
        
    elif client and re.match(r'C[A-Z]{3}', line[0:4]):
        cmd, data = line.split(" ", 1)
    elif line[0] == "<":
        cmd = "GlobalTo"
        data = line
    else:
        cmd = "Chat"
        data = line
    if cmd == "To:":
        cmd = "To"
    return cmd, data

def parseAddr(line):
    """
    Take a string "192.168.1.42:4242" and return
    ("192.168.1.42", 4242,)    
    """
    if line.count(":"):
        host, port = line.split(":",1)
    else:
        host = line
        port = 411
    port = int(port)
    return host, port

