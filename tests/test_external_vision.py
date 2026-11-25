import unittest
from visionbot.external_session import computer_title,EXTERNAL

class ExternalVisionTests(unittest.TestCase):
    def test_title(self):
        self.assertTrue(computer_title('Play Chess Against the Computer - Chess.com'))
        self.assertTrue(computer_title('Играть с компьютером - Chess.com'))
        self.assertFalse(computer_title('Play Chess Online - Chess.com'))
        self.assertFalse(computer_title('Rated Computer - Chess.com'))
        self.assertFalse(computer_title('Computer - other site'))
    def test_engines(self):
        self.assertEqual(set(EXTERNAL.values()),{'stockfish','lc0'})
if __name__=='__main__':unittest.main()
