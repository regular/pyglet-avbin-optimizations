#!/usr/bin/env python

'''
'''

__docformat__ = 'restructuredtext'
__version__ = '$Id$'

import sys
import re

from ctypes import *

from pyglet.GL.VERSION_1_1 import *
from pyglet.image.codecs import *

class Image(object):
    '''Abstract class representing image data.
    '''

    def __init__(self, width, height):
        self.width = width
        self.height = height

    def get_texture(self, internalformat=None):
        '''Return a Texture of this image.  This method does not cache
        textures, it will create a new one each time it is called.
        internalformat can be a valid argument to glTexImage2D to specify
        how the image is stored internally, or to specify internal
        compression.
        '''
        raise NotImplementedError()

    def texture_subimage(self, x, y):
        '''Copy the image into the current texture at the given coordinates.
        '''
        raise NotImplementedError()

    @staticmethod
    def load(filename=None, file=None):
        if not file:
            file = open(filename, 'rb')

        for decoder in get_decoders(filename):
            try:
                image = decoder.decode(file, filename)
                return image
            except ImageDecodeException:
                file.seek(0)

        if filename:
            raise ImageDecodeException('No decoder could load %r' % filename)
        else:
            raise ImageDecodeException('No decoder could load %r' % file)

    @staticmethod
    def create_checkerboard(size, 
                          colour1=(150, 150, 150, 255), 
                          colour2=(200, 200, 200, 255)):
        half = size/2
        colour1 = '%c%c%c%c' % colour1
        colour2 = '%c%c%c%c' % colour2
        row1 = colour1 * half + colour2 * half
        row2 = colour2 * half + colour1 * half
        data = row1 * half + row2 * half
        return RawImage(data, size, size, GL_RGBA, GL_UNSIGNED_BYTE)

class RawImage(Image):
    '''Encapsulate image data stored in an OpenGL pixel format.
    '''

    def __init__(self, data, width, height, format, type):
        '''Initialise image data.

        data
            String or array/list of bytes giving the decoded data.
        width, height
            Width and height of the image, in pixels
        format
            A valid format argument to glTexImage2D, for example
            GL_RGB, GL_LUMINANCE_ALPHA, etc.
        type
            A valid type argument to glTexImage2D, for example
            GL_UNSIGNED_BYTE, etc.

        '''
        super(RawImage, self).__init__(width, height)
        self.data = data
        self.format = format
        self.type = type

    def get_texture(self, internalformat=None):
        tex_width, tex_height, u, v = \
            Texture.get_texture_size(self.width, self.height)
        if not internalformat:
            if self.format in (GL_LUMINANCE, GL_LUMINANCE_ALPHA, GL_ALPHA):
                internalformat = self.format
            elif self.format in (GL_RGBA, GL_BGRA):
                internalformat = GL_RGBA
            else:
                internalformat = GL_RGB

        id = c_uint()
        glGenTextures(1, byref(id))
        glBindTexture(GL_TEXTURE_2D, id.value)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        if tex_width == self.width and tex_height == self.height:
            glTexImage2D(GL_TEXTURE_2D, 
                0, 
                internalformat,
                tex_width, tex_height,
                0,
                self.format, self.type,
                self.data)
        else:
            blank = (c_byte * tex_width * tex_height)()
            glTexImage2D(GL_TEXTURE_2D,
                0,
                internalformat,
                tex_width,
                tex_height,
                0,
                GL_RED,
                GL_UNSIGNED_BYTE,
                blank)
            self.texture_subimage(0, 0)
        return Texture(id, self.width, self.height, u, v)

    def texture_subimage(self, x, y):
        glTexSubImage2D(GL_TEXTURE_2D,
            0,
            x, y,
            self.width, self.height,
            self.format, self.type,
            self.data)


def _nearest_pow2(n):
    i = 1
    while i < n:
        i <<= 1
    return i

class Texture(object):
    def __init__(self, id, width, height, u, v):
        self.id = id
        self.width, self.height = width, height
        self.uv = u, v

        # Make quad display list
        self.quad_list = glGenLists(1)
        glNewList(self.quad_list, GL_COMPILE)
        glBindTexture(GL_TEXTURE_2D, self.id)
        glPushAttrib(GL_ENABLE_BIT)
        glEnable(GL_TEXTURE_2D)

        glBegin(GL_QUADS)
        glTexCoord2f(0, 0)
        glVertex2f(0, 0)
        glTexCoord2f(0, self.uv[1])
        glVertex2f(0, self.height)
        glTexCoord2f(self.uv[0], self.uv[1])
        glVertex2f(self.width, self.height)
        glTexCoord2f(self.uv[0], 0)
        glVertex2f(self.width, 0)
        glEnd()

        glPopAttrib()
        glEndList()

    # TODO: <ah> I think this should be a sprite function only: 3D games
    #       will have no need for this DL.
    def draw(self):
        glCallList(self.quad_list)

    @staticmethod
    def get_texture_size(width, height):
        '''Return the texture size that should be used to hold an image
        of the given size.  On older cards this should be rounded up to
        2^n dimensions.  On newer cards this is not necessary.

        Returns (width, height, u, v)
        '''
        # TODO detect when non-power2 textures are permitted.
        # TODO square textures required by some cards?
        tex_width = _nearest_pow2(width)
        tex_height = _nearest_pow2(height)
        u = float(width) / tex_width
        v = float(height) / tex_height
        return tex_width, tex_height, u, v


class AtlasSubTexture(object):
    def __init__(self, quad_list, width, height, uv):
        self.quad_list = quad_list
        self.width, self.height = width, height
        self.uv = uv

    def draw(self):
        glPushAttrib(GL_ENABLE_BIT)
        glEnable(GL_TEXTURE_2D)
        glCallList(self.quad_list)
        glPopAttrib()

class TextureAtlasRects(object):
    def __init__(self, id, width, height, uv, rects):
        self.size = (width, height)
        self.id = id
        self.uvs = []
        self.quad_lists = []
        self.elem_sizes = []

        n = glGenLists(len(rects))
        self.quad_lists = range(n, n + len(rects))
        for i, rect in enumerate(rects):
            u = float(rect[0]) / width * uv[0]
            v = float(rect[1]) / height * uv[1]
            du = float(rect[2]) / width * uv[0]
            dv = float(rect[3]) / height * uv[1]
            elem_uv = (u, v, u + du, v + dv)
            elem_size = (rect[2], rect[3])

            glNewList(self.quad_lists[i], GL_COMPILE)
            glBindTexture(GL_TEXTURE_2D, self.id)
            glBegin(GL_QUADS)
            glTexCoord2f(u, v)
            glVertex2f(0, 0)
            glTexCoord2f(u + du, v)
            glVertex2f(elem_size[0], 0)
            glTexCoord2f(u + du, v + dv)
            glVertex2f(elem_size[0], elem_size[1])
            glTexCoord2f(u, v + dv)
            glVertex2f(0, elem_size[1])
            glEnd()
            glEndList()

            self.uvs.append(elem_uv)
            self.elem_sizes.append(elem_size)

    @classmethod
    def from_data(cls, data, width, height, bpp, rects=[]):
        id, uv = _get_texture(data, width, height, bpp)
        return cls(id, width, height, uv, rects)

    @classmethod
    def from_image(cls, image, rects=[]):
        id, uv = _get_texture(image.data, image.width, image.height,
            image.bpp)
        return cls(id, image.width, image.height, uv, rects)

    def draw(self, index):
        glPushAttrib(GL_ENABLE_BIT)
        glEnable(GL_TEXTURE_2D)
        glCallList(self.quad_lists[index])
        glPopAttrib()

    def get_size(self, index):
        return self.elem_sizes[index]

    def get_quad(self, index):
        return self.elem_sizes[index], self.uvs[index]

    def get_texture(self, index):
        '''Return something that smells like a Texture instance.'''
        w, h = self.elem_sizes[index]
        return AtlasSubTexture(self.quad_lists[index], w, h, self.uvs[index])


class TextureAtlasGrid(object):
    def __init__(self, id, width, height, uv, rows=1, cols=1):
        assert rects or (rows >= 1 and cols >= 1)
        self.size = (width, height)
        self.id = id
        self.uvs = []
        self.quad_lists = []
        self.elem_sizes = []

        self.rows = rows
        self.cols = cols

        elem_size = width / cols, height / rows
        n = glGenLists(rows * cols)
        self.quad_lists = range(n, n + rows * cols)
        du = uv[0] / cols
        dv = uv[1] / rows
        i = v = 0
        for row in range(rows):
            u = 0
            for col in range(cols):
                glNewList(self.quad_lists[i], GL_COMPILE)
                glBindTexture(GL_TEXTURE_2D, self.id)
                glBegin(GL_QUADS)
                glTexCoord2f(u, v)
                glVertex2f(0, 0)
                glTexCoord2f(u + du, v)
                glVertex2f(elem_size[0], 0)
                glTexCoord2f(u + du, v + dv)
                glVertex2f(elem_size[0], elem_size[1])
                glTexCoord2f(u, v + dv)
                glVertex2f(0, elem_size[1])
                glEnd()
                glEndList()

                elem_uv = (u, v, u + du, v + dv)
                self.uvs.append(elem_uv)
                self.elem_sizes.append(elem_size)
                u += du
                i += 1
            v += dv

    @classmethod
    def from_data(cls, data, width, height, bpp, rows=1, cols=1):
        id, uv = _get_texture(data, width, height, bpp)
        return cls(id, width, height, uv, rows, cols)

    @classmethod
    def from_image(cls, image, rows=1, cols=1):
        id, uv = _get_texture(image.data, image.width, image.height,
            image.bpp)
        return cls(id, image.width, image.height, uv, rows, cols)

    def draw(self, row, col):
        glPushAttrib(GL_ENABLE_BIT)
        glEnable(GL_TEXTURE_2D)
        glCallList(self.quad_lists[row * self.cols + col])
        glPopAttrib()

    def get_size(self, row, col):
        return self.elem_sizes[row * self.cols + col]

    def get_quad(self, row, col):
        i = row * self.cols + col
        return self.elem_sizes[i], self.uvs[i]

# Initialise default codecs
add_default_image_codecs()
