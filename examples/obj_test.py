#!/usr/bin/env python

'''
'''

__docformat__ = 'restructuredtext'
__version__ = '$Id: obj_test.py 111 2006-10-20 06:39:12Z r1chardj0n3s $'

import os
import ctypes
import pyglet.window
from pyglet.window.event import *

from pyglet.GL.VERSION_1_1 import *
from pyglet.GLU.VERSION_1_1 import *
from pyglet import clock
from pyglet.model import obj

w1 = pyglet.window.create(200, 200)

exit_handler = ExitHandler()
w1.push_handlers(exit_handler)

c = clock.Clock()

fourfv = ctypes.c_float * 4
c_float_p = ctypes.POINTER(ctypes.c_float)
glLightfv(GL_LIGHT0, GL_POSITION,
    ctypes.cast(fourfv(100, 200, 100, 0), c_float_p))
glLightfv(GL_LIGHT0, GL_AMBIENT,
    ctypes.cast(fourfv(0.2, 0.2, 0.2, 1.0), c_float_p))
glLightfv(GL_LIGHT0, GL_DIFFUSE,
    ctypes.cast(fourfv(0.5, 0.5, 0.5, 1.0), c_float_p))
glEnable(GL_LIGHT0)
glEnable(GL_LIGHTING)
glEnable(GL_DEPTH_TEST)

def resize(width, height):
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(60., float(width)/height, 1., 100.)
    glMatrixMode(GL_MODELVIEW)
w1.push_handlers(on_resize=resize)
resize(200, 200)

glClearColor(0, 0, 0, 0)

bunny = obj.OBJ(os.path.join(os.path.split(__file__)[0], 'rabbit.obj'))

r = 0
while not exit_handler.exit:
    c.set_fps(60)
    w1.dispatch_events()

    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glLoadIdentity()
    gluLookAt(0, 5, 5, 0, 1, -1, 0, 1, 0)

    r += 1
    if r > 360: r = 0
    glRotatef(r, 0, 1, 0)
    bunny.draw()

    w1.flip()

