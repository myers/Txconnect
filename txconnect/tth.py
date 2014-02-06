# Copyright 2008 Corbin Simpson <cds@corbinsimpson.com>
# Copyright 2010 Myers Carpenter <myers@maski.org>
# This code is provided under the terms of the GNU Public License, version 3.

import os, base64, math

import tiger

class TTH:
    """A class describing a Tiger Tree Hash tree."""
    blocksize = 1024 
    one_mebibyte = 2**20
    
    def __init__(self, fileName=None, maxlevels=0, leaves=None, root=None, fileSize=None):
        self.initleaves = None
        if leaves:
            if len(leaves) % 24 != 0:
                raise ValueError('len(leaves) should a multiple of 24')
            self.initleaves = []
            for ii in range(len(leaves) / 24):
                self.initleaves.append(leaves[ii*24:ii*24+24])
            
        self.root = root
        self.fileName = fileName
        self.fileSize = fileSize
        
        self.inited = False
        self.maxlevels = maxlevels
        if not self.initleaves and fileName:
            self.fileSize = os.path.getsize(fileName)
            self.buildTreeFromFile(fileName)
        if self.initleaves and self.root:
            self.verifyRoot()

    def buildTreeFromFile(self, fileName):
        leaves = self.hash(fileName)
        self.levels, self.tree = self.buildTree(leaves)
        self.inited = True
                
    def verifyRoot(self):
        self.levels, self.tree = self.buildTree(self.initleaves)
        if self.root != self.getroot():
            raise ValueError('root does not match leave data')
        

    def hash(self, f):
        """Build the tree."""

        if self.inited:
            return

        h = open(f, "rb")
        leaves = []
        # Need to read once, to figure out if file's empty.
        # This part is really lame.
        buf = h.read(self.blocksize)
        if not len(buf):
            leaves.append(tiger.new("\x00").digest())
        else:
            while len(buf):
                buf = '\x00' + buf
                leaves.append(tiger.new(buf).digest())
                buf = h.read(self.blocksize)

        h.close()
        return leaves

    def buildTree(self, leaves):
        levels = int(math.ceil(math.log(len(leaves),2)))
        tree = [leaves]

        for i in range(levels):
            l = []

            for j in range(len(tree[i])):

                if j % 2:
                    continue
    
                try:
                    buf = '\x01' + tree[i][j] + tree[i][j+1]
                    l.append(tiger.new(buf).digest())
                except IndexError:
                    l.append(tree[i][j])

            tree.append(l)

        tree.reverse()
        if self.maxlevels:
            del tree[self.maxlevels:]
        return levels, tree

    def gettree(self):
        if self.inited:
            return self.tree

    def getroot(self):
        if self.tree is not None:
            return base64.b32encode(self.tree[0][0])[:-1]

    def dump(self):
        if self.fileSize:
            print "Levels: %d" % (self.computeLevels(),)
        print "Levels with data: %d" % (len(self.tree),)
        for i in range(len(self.tree)):
            print "Level", i, ":", [base64.b32encode(j) for j in self.tree[i]]

    def computeLevels(self):
        numOfLeaves = math.ceil(self.fileSize/float(self.blocksize))
        return int(math.ceil(math.log(numOfLeaves, 2))) + 1

    def getleaves(self, blockSize=one_mebibyte):
        if self.fileSize == 0:
            return ''
        for ii in range(len(self.tree)):
            if self.blockSize(ii) < blockSize:
                return ''
            if self.blockSize(ii) == blockSize:
                return ''.join(self.tree[ii])
    
    """
    get the block size for a level.  if no level specified, then give the lowest level we have
    """
    def blockSize(self, level=None):
        if level is None:
            level = len(self.tree) - 1
        levels = self.computeLevels() - 1
        return self.blocksize * (2 ** (levels - level))

    def blockCount(self, level=None):
        if level is None:
            level = len(self.tree) - 1
        bs = self.blockSize(level)
        return int(math.ceil(self.fileSize/float(bs)))
    
    """
    @returns [(startingByte, byteCount,), ...]
    """
    def blocksNeeded(self):
        ret = []

        bc = self.blockCount()
        bs = self.blockSize()
        
        if not os.path.exists(self.fileName):
            for ii in range(bc-1):
                ret.append((bs*ii, bs,))
            ret.append((bs*(bc-1), self.fileSize - (bs*(bc-1)),))
            return ret
        
        assert os.path.getsize(self.fileName) == self.fileSize, "%r %r %r" % (self.fileName, os.path.getsize(self.fileName), self.fileSize,)
        leaves = self.hash(self.fileName)
        levelCount, tree = self.buildTree(leaves)
        
        level = len(self.tree) - 1
        for ii in range(len(self.tree[level])):
            if self.tree[level][ii] != tree[level][ii]:
                if ii == bc - 1:
                    ret.append((bs*ii, self.fileSize - (bs*ii),))
                    break
                ret.append((bs*ii, bs,))
        
        return ret
        