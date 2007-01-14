#!/usr/bin/env python

'''
Draw OpenGL textures in 2d scenes
=================================

---------------
Getting Started
---------------

You may create a drawable image with:

    >>> from pyglet.scene2d import *
    >>> i = Image2d.load('kitten.jpg')
    >>> i.draw()

'''

__docformat__ = 'restructuredtext'
__version__ = '$Id$'

from pyglet.GL.VERSION_1_1 import *

from pyglet.image import RawImage

from pyglet.resource import register_factory, ResourceError


@register_factory('imageatlas')
def imageatlas_factory(resource, tag):
    filename = resource.find_file(tag.getAttribute('file'))
    if not filename:
        raise ResourceError, 'No file= on <imageatlas> tag'
    atlas = Image2d.load(filename)
    atlas.properties = resource.handle_properties(tag)
    if tag.hasAttribute('id'):
        atlas.id = tag.getAttribute('id')
        resource.add_resource(atlas.id, atlas)

    # figure default size if specified
    if tag.hasAttribute('size'):
        d_width, d_height = map(int, tag.getAttribute('size').split('x'))
    else:
        d_width = d_height = None

    for child in tag.childNodes:
        if not hasattr(child, 'tagName'): continue
        if child.tagName != 'image':
            raise ValueError, 'invalid child'

        if child.hasAttribute('size'):
            width, height = map(int, child.getAttribute('size').split('x'))
        elif d_width is None:
            raise ValueError, 'atlas or subimage must specify size'
        else:
            width, height = d_width, d_height

        x, y = map(int, child.getAttribute('offset').split(','))
        image = atlas.subimage(x, y, width, height)
        id = child.getAttribute('id')
        resource.add_resource(id, image)

    image.properties = resource.handle_properties(tag)

    if tag.hasAttribute('id'):
        image.id = tag.getAttribute('id')
        resource.add_resource(image.id, image)
        
    return atlas


@register_factory('image')
def image_factory(resource, tag):
    filename = resource.find_file(tag.getAttribute('file'))
    if not filename:
        raise ResourceError, 'No file= on <image> tag'
    image = Image2d.load(filename)

    image.properties = resource.handle_properties(tag)

    if tag.hasAttribute('id'):
        image.id = tag.getAttribute('id')
        resource.add_resource(image.id, image)

    return image


class Drawable(object):
    ''' A draw()'able thing that might have additional (possibly animated)
    effects attached.
    '''
    def __init__(self):
        self.effects = []

    def set_effect(self, effect):
        self.effects = [effect]
    def add_effect(self, effect):
        self.effects.append(effect)
    def remove_effect(self, effect):
        self.effects.remove(effect)

    def animate(self, dt):
        for effect in self.effects:
            if effect.animate is not None:
                # XXX detect end of animation
                effect.animate(dt)

    def draw(self):
        if self.effects:
            self.effects[-1].draw(self)
        else:
            self.impl_draw()

    def impl_draw(self, colour=None):
        '''Implementation of drawing by a subclass.

        If "colour" is not None it should be used to tint the drawing.
        '''
        raise NotImplemented()

class TintEffect(object):
    '''Changes the current colour, thus tinting the drawable being applied
    to. Requires that the drawable be texture-mapped and that it not
    specify its own colour.
    '''
    animate = None
    def __init__(self, colour):
        self.colour = colour

    def draw(self, drawable):
        glPushAttrib(GL_CURRENT_BIT)
        glColor4f(*self.colour)
        drawable.impl_draw()
        glPopAttrib()


class Image2d(Drawable):
    def __init__(self, texture, x, y, width, height):
        Drawable.__init__(self)
        self.texture = texture
        self.x, self.y = x, y
        self.width, self.height = width, height

    @classmethod
    def load(cls, filename=None, file=None):
        '''Image is loaded from the given file.'''
        image = RawImage.load(filename=filename, file=file)
        image = cls(image.texture(), 0, 0, image.width, image.height)
        image.filename = filename
        return image

    @classmethod
    def from_image(cls, image):
        return cls(image.texture(), 0, 0, image.width, image.height)

    @classmethod
    def from_texture(cls, texture):
        '''Image is the entire texture.'''
        return cls(texture, 0, 0, texture.width, texture.height)

    @classmethod
    def from_subtexture(cls, texture, x, y, width, height):
        '''Image is a section of the texture.'''
        return cls(texture, x, y, width, height)

    __quad_list = None
    def quad_list(self):
        if self.__quad_list is not None:
            return self.__quad_list

        # textures are upside-down so we need to compensate for that
        # XXX make textures not lie about their size
        tw, th = self.texture.width, self.texture.height
        tw, th, x, x = self.texture.get_texture_size(tw, th)
        l = float(self.x) / tw
        b = float(self.y) / th
        r = float(self.x + self.width) / tw
        t = float(self.y + self.height) / th

        # Make quad display list
        self.__quad_list = glGenLists(1)
        glNewList(self.__quad_list, GL_COMPILE)
        glBindTexture(GL_TEXTURE_2D, self.texture.id)
        glPushAttrib(GL_ENABLE_BIT)
        glEnable(GL_TEXTURE_2D)

        glBegin(GL_QUADS)
        glTexCoord2f(l, b)
        glVertex2f(0, 0)
        glTexCoord2f(l, t)
        glVertex2f(0, self.height)
        glTexCoord2f(r, t)
        glVertex2f(self.width, self.height)
        glTexCoord2f(r, b)
        glVertex2f(self.width, 0)
        glEnd()

        glPopAttrib()
        glEndList()
        return self.__quad_list
    quad_list = property(quad_list)

    def impl_draw(self):
        glCallList(self.quad_list)

    def subimage(self, x, y, width, height):
        # XXX should we care about recursive sub-image calls??
        return self.__class__(self.texture, x, y, width, height)

