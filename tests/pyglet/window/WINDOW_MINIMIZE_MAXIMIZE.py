#!/usr/bin/env python

'''Test that window can be minimized and maximized.

Expected behaviour:
    One window will be opened.

     - press "x" to maximize the window.
     - press "n" to minimize the window.

    Close the window or press ESC to end the test.
'''

__docformat__ = 'restructuredtext'
__version__ = '$Id: $'

import unittest

import pyglet.window
from pyglet.window.event import *
from pyglet.window.key import *

class WINDOW_MINIMIZE_MAXIMIZE(unittest.TestCase):
    def on_keypress(self, symbol, modifiers):
        if symbol == K_X:
            self.w.maximize()
            print 'Window maximized.'
        elif symbol == K_N:
            self.w.minimize()
            print 'Window minimized.'

    def test_minimize_maximize(self):
        self.width, self.height = 200, 200
        self.w = w = pyglet.window.create(self.width, self.height)
        exit_handler = ExitHandler()
        w.push_handlers(exit_handler)
        w.push_handlers(self)
        while not exit_handler.exit:
            w.dispatch_events()
        w.close()

if __name__ == '__main__':
    unittest.main()
