from twisted.trial import unittest

from ..directconnect import utils

class TestKey(unittest.TestCase):
    def testKey(self):
        testlock = "EXTENDEDPROTOCOLRTx[5gGFJ3upR;^Gm9<NkI5HXH1c= Pk=monkey"
        testkey = "\xe1\xd1\xc0\x11\xb0\xa0\x10\x10\x41\x20\xd1\xb1\xb1\xc0\xc0\x30\xe1\x2f\x25\x44\x43\x4e\x30\x39\x36\x25\x2f\xc2\x32\xe6\x25\x02\x10\xc0\x97\x64\x50\x22\x96\x56\x91\xa2\x45\x50\x27\x52\x22\xc7\xd7\x01\x01\x97\x25\xe5"
        self.assertEquals(utils.lockToKey(testlock), testkey)

        testlock = "Sending_key_isn't_neccessary,_key_won't_be_checked. Pk=monkey"
        testkey = "\xc1c\xb0\xa0\xd0p\x90\x83C\xe0\xc1bc\xa1\xd1\x945\xb2\x13\xb0/%DCN096%//%DCN000%//%DCN096%/a/%DCN000%/!1\xb0U7C\xe0\xc1b\x82\x81\x10\x945\xb2\xd3p\xa3\xc3\xb0\xd0/%DCN096%/\x80\xe0\x10\xa4"
        self.assertEquals(utils.lockToKey(testlock), testkey)


        testkey_from_revconnect = "\xc1\x63\xb0\xa0\xd0\x70\x90\x83\x43\xe0\xc1\x62\x63\xa1\xd1\x94\x35\xb2\x13\xb0\x2f\x25\x44\x43\x4e\x30\x39\x36\x25\x2f\x2f\x25\x44\x43\x4e\x30\x30\x30\x25\x2f\x2f\x25\x44\x43\x4e\x30\x39\x36\x25\x2f\x61\x2f\x25\x44\x43\x4e\x30\x30\x30\x25\x2f\x21\x31\xb0\x55\x37\x43\xe0\xc1\x62\x82\x81\x10\x94\x35\xb2\xd3\x70\xa3\xc3\xb0\xd0\x2f\x25\x44\x43\x4e\x30\x39\x36\x25\x2f\x80\xe0\x10\xa4"
        assert testkey == testkey_from_revconnect

        testlock = "\x45\x58\x54\x45\x4e\x44\x45\x44\x50\x52\x4f\x54\x4f\x43\x4f\x4c\x71\x62\x33\x3e\x62\x74\x50\x46\x34\x73\x3e\x71\x5a\x5a\x5a\x45\x79\x3a\x4c\x66\x41\x4d\x3c\x4d\x5b\x47\x52\x4b\x3c Pk=monkey"
        testkey = "\x73\xd1\xc0\x11\xb0\xa0\x10\x10\x41\x20\xd1\xb1\xb1\xc0\xc0\x30\xd3\x31\x15\xd0\xc5\x61\x42\x61\x27\x74\xd4\xf4\xb2\x2f\x25\x44\x43\x4e\x30\x30\x30\x25\x2f\x2f\x25\x44\x43\x4e\x30\x30\x30\x25\x2f\xf1\xc3\x34\x67\xa2\x72\xc0\x17\x17\x61\xc1\x51\x91\x77"
        self.assertEquals(utils.lockToKey(testlock), testkey)

        testlock = "\x45\x58\x54\x45\x4e\x44\x45\x44\x50\x52\x4f\x54\x4f\x43\x4f\x4c\x58\x4a\x71\x30\x63\x6c\x79\x68\x53\x56\x3e\x72\x62\x33\x4a\x76\x74\x6b\x63\x48\x4a\x53\x4a\x3a\x35\x48\x40\x39\x4a Pk=monkey"
        testkey = "\x33\xd1\xc0\x11\xb0\xa0\x10\x10\x41\x20\xd1\xb1\xb1\xc0\xc0\x30\x41\x21\xb3\x14\x35\xf0\x51\x11\xb3\x50\x86\xc4\x01\x15\x97\xc3\x20\xf1\x80\xb2\x20\x91\x91\x07\xf0\xd7\x80\x97\x37"
        self.assertEquals(utils.lockToKey(testlock), testkey)

        testlock = 'EXTENDEDPROTOCOL::This_hub_was_written_by_Yoshi::CTRL[\xa5\x7f\xca\x08\xe6] Pk=monkey'
        testkey =  "\xbf\xd1\xc0\x11\xb0\xa0\x10\x10\x41\x20\xd1\xb1\xb1\xc0\xc0\x30\x67\x2f\x25\x44\x43\x4e\x30\x30\x30\x25\x2f\xe6\xc3\x10\xa1\xc2\x73\xd1\x71\xd3\x82\x61\x21\xc2\x82\x50\xb1\xd1\x2f\x25\x44\x43\x4e\x30\x30\x30\x25\x2f\x11\xb0\x13\xd3\xb1\x62\x2f\x25\x44\x43\x4e\x30\x39\x36\x25\x2f\x63\xc1\xb1\x10\x35\x2f\x25\x44\x43\x4e\x30\x30\x30\x25\x2f\x97\x71\x2f\x25\x44\x43\x4e\x30\x39\x36\x25\x2f\xe1\x71\xef\xad\x5b\x2c\xee\xbb"
        self.assertEquals(utils.lockToKey(testlock), testkey)

        testlock = 'EXTENDEDPROTOCOL::This_hub_was_written_by_Yoshi::CTRL[\xed\x80\xd1\x08\xe6] Pk=monkey'
        testkey =  "\xbf\xd1\xc0\x11\xb0\xa0\x10\x10\x41\x20\xd1\xb1\xb1\xc0\xc0\x30\x67\x2f\x25\x44\x43\x4e\x30\x30\x30\x25\x2f\xe6\xc3\x10\xa1\xc2\x73\xd1\x71\xd3\x82\x61\x21\xc2\x82\x50\xb1\xd1\x2f\x25\x44\x43\x4e\x30\x30\x30\x25\x2f\x11\xb0\x13\xd3\xb1\x62\x2f\x25\x44\x43\x4e\x30\x39\x36\x25\x2f\x63\xc1\xb1\x10\x35\x2f\x25\x44\x43\x4e\x30\x30\x30\x25\x2f\x97\x71\x2f\x25\x44\x43\x4e\x30\x39\x36\x25\x2f\xe1\x71\x6b\xd6\x15\x9d\xee\xbb"
        self.assertEquals(utils.lockToKey(testlock), testkey)
        
