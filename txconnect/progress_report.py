import sys, os 

__all__ = ['progress_report']

def getTerminalSize():
    def ioctl_GWINSZ(fd):
        try:
            import fcntl, termios, struct
            cr = struct.unpack('hh', fcntl.ioctl(fd, termios.TIOCGWINSZ, '1234'))
        except:
            return None
        return cr
    cr = ioctl_GWINSZ(0) or ioctl_GWINSZ(1) or ioctl_GWINSZ(2)
    if not cr:
        try:
            fd = os.open(os.ctermid(), os.O_RDONLY)
            cr = ioctl_GWINSZ(fd)
            os.close(fd)
        except:
            pass
    if not cr:
        try:
            cr = (os.environ['LINES'], os.environ['COLUMNS'])
        except:
            cr = (25, 80)
    return int(cr[1]), int(cr[0])

def progress_report(*args):
    if not sys.stdin.isatty():
        return
    report = ' '.join([str(aa) for aa in args])
    cols, lines = getTerminalSize()
    sys.stdout.write("\r%s" % (report[:cols].ljust(cols),))
    sys.stdout.flush()
