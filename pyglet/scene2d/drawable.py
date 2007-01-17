from pyglet.GL.VERSION_1_1 import *
 
class DrawEnv(object):
    '''Sets up drawing environment.

    My have either or both of a "before" and "after" method.
    '''
    pass
 
class DrawBlended(DrawEnv):
    '''Sets up texture env for an alpha-blended draw.
    '''
    def before(self):
        glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def after(self):
        glPopAttrib()
DRAW_BLENDED = DrawBlended()
 
class Drawable(object):
    effects = []
 
    def get_drawstate(self):
        raise NotImplemented('implement on subclass')
 
    def get_style(self):
        style = self.get_drawstyle()
        for effect in self.effects:
            style = effect.apply(style)
        return style

    def draw(self):
        '''Convenience method.

        Don't use this if you have a lot of drawables and care about
        performance. Collect up your drawables in a list and pass that to
        draw_many().
        '''
        self.get_style().draw()


class Effect:
    def apply(self, style):
        '''Modify some aspect of the style. If style.is_copy is False then
        .copy() it. We don't do that automatically because there's a chance
        this method is a NOOP.
        '''
        raise NotImplemented()
 
class TintEffect(Effect):
    '''Apply a tint to the Drawable:

    For each component RGBA:

        resultant color = drawable.color * tint.color
    '''
    def __init__(self, tint):
        self.tint = tint
    def apply(self, style):
        style = style.copy()
        style.color = tuple([style.color[i] * self.tint[i] for i in range(4)])
        return style
 

class DrawStyle(object):
    __slots__ = ' color x y z width height texture uvs draw_list draw_env draw_func is_copy'.split()

    def __init__(self, color=None, texture=None, x=None, y=None, z=0,
            width=None, height=None, uvs=None, draw_list=None,
            draw_env=None, draw_func=None):
        self.color = color
        self.x, self.y, self.z = x, y, z
        self.width, self.height = width, height

        self.texture = texture
        if texture is not None and uvs is None:
            raise ValueError('texture and uvs must both be supplied')
        self.uvs = uvs
        if uvs is not None and texture is None:
            raise ValueError('texture and uvs must both be supplied')

        self.draw_list = draw_list
        self.draw_env = draw_env
        self.draw_func = draw_func
        self.is_copy = False
 
    def copy(self):
        s = DrawStyle(**self.__dict__)
        s.is_copy = True
        return s
 
    def draw(self):

        if self.color is not None:
            glColor4f(*self.color)
        
        if self.texture is not None:
            glBindTexture(GL_TEXTURE_2D, self.texture.id)

        if hasattr(self.draw_env, 'before'):
            self.draw_env.before()

        if self.x is not None and self.y is not None:
            glPushMatrix()
            glTranslatef(self.x, self.y, 0)

        if self.draw_func is not None:
            self.draw_func()

        if self.draw_list is not None:
            glCallList(self.draw_list)

        if hasattr(self.draw_env, 'after'):
            self.draw_env.after()

        if self.x is not None and self.y is not None:
            glPopMatrix()

    def __cmp__(self, other):
        print (self, other)
        return (
            cmp(self.color, other.color),
            cmp(self.texture.id, other.texture.id),
            cmp(self.draw_env, other.draw_env),
            cmp(self.draw_func, other.draw_func),
            cmp(self.draw_list, other.draw_list)
        )


def draw_many(drawables):
    styles = [d.get_drawstyle() for d in drawables]
    drawables.sort()
    old_color = None
    old_texture = None
    old_env = None
    for d in styles:
        if d.color != old_color:
            glColor4f(*d.color)
            old_color = d.color
        if d.texture != old_texture:
            glBindTexture(GL_TEXTURE_2D, d.texture.id)
            old_texture = d.texture.id
        if d.draw_env != old_env:
            if old_env is not None and hasattr(old_env, 'after'):
                old_env.after()
            if hasattr(d.draw_env, 'before'):
                d.draw_env.before()
            old_env = d.draw_env
        if d.x is not None and d.y is not None:
            glPushMatrix()
            glTranslatef(d.x, d.y, 0)
        if d.draw_list is not None:
            glCallList(d.draw_list)
        if d.draw_func is not None:
            d.draw_func()
        if d.x is not None and d.y is not None:
            glPopMatrix()

    if old_env is not None and hasattr(old_env, 'after'):
        old_env.after()
