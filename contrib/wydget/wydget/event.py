'''Implement event handling for wydget GUIs.

The `GUIEventDispatcher` class is automatically mixed into the `wydget.GUI`
class and is activated by pushing the gui onto a window's event handlers
stack::

    gui = GUI(window)
    window.push_handlers(gui)

Standard pyglet events are passed through if handled. The first argument is
always the active element (see below `determining the active element`_):

- `on_mouse_motion(element, x, y, dx, dy)`
- `on_mouse_press(element, x, y, button, modifiers)`
- `on_mouse_release(element, x, y, button, modifiers)`
- `on_mouse_drag(element, x, y, dx, dy, buttons, modifiers)`
- `on_mouse_scroll(element, x, y, dx, dy)`
- `on_key_press(element, symbol, modifiers)`
- `on_text(element, text)`
- `on_text_motion(element, motion)`
- `on_text_motion_select(element, motion)`
  
New events generated by wydget:

`on_change(element, value)`
   The element's "value" changed (eg. text in a TextInput, selection
   choice for a Selection)

`on_click(element, x, y, buttons, modifiers, click_count)`
   The element was clicked. the click_count argument indicates how
   many times the element has been clicked in rapid succession.

`on_element_enter(element, x, y)`
   The mouse is over the element. Note that this event will be
   automatically propogated to all parents of the element directly under
   the mouse.
   
   If an element implements the `on_element_enter` handler but does not
   wish to receive an `on_element_leave` event when the mouse
   departs it should return `EVENT_UNHANDLED`. Returning `EVENT_HANDLED`
   implies that `on_element_leave` be generated once the mouse leaves the
   element.

`on_element_leave(element, x, y)`
   The mouse is no longer over the element.

`on_drag(element, x, y, dx, dy, buttons, modifiers)`
   Press on listening element followed by mouse movement. If the handler
   returns `EVENT_UNHANDLED` then the element is not considered to be being
   dragged, and thus no further `on_drag_*` events will be generated, nor
   an `on_drop`.

`on_drag_enter(element, x, y, dragged_element)`
   The dragged_element is being dragged over the stationary element.

`on_drag_leave(element, x, y, dragged_element)`
   The dragged_element is no longer being dragged over the
   stationary element.

`on_drag_complete(element, x, y, buttons, modifiers, ok)`
   Release after dragging listening element, ok is return code
   from dropped-on element's `on_drop`.

`on_drop(element, x, y, button, modifiers, element)`
   Element has been drag-n-dropped on listening element.

`on_gain_focus(element)`
   Listening element gains focus.

`on_lose_focus(element)`
   Listening element loses focus.


Determining the Active Element
------------------------------

The active element - the one which is passed into the event handlers above
- is usually the element directly under the mouse. There are some
situations where this is not the case:

- ``element.is_transparent == True``
- ``element.isEnabled() == False``
- `on_text`, `on_text_motion` and `on_text_motion_select` are passed to the
  *currently focused element* regardless of the mouse position
- in all other cases, the event may be propogated (see `event propogation`_
  below)


Event Propogation
-----------------

Events are automatically propogated up to element parents if an event
handler either does not exist or the handler returns `EVENT_UNHANDLED`.

'''

import inspect
import time

from pyglet.event import (EventDispatcher, EVENT_UNHANDLED, EVENT_HANDLED,
    EventException)
from pyglet.window import key

from layout.css import Rule, RuleSet, Selector, SimpleSelector

# partially snarfed from layout.gl.event
# Instead of each stack layer being a dictionary mapping event-name to
# event-function, each layer is a dictionary mapping event-name to 
# RuleSet

class GUIEventDispatcher(EventDispatcher):

    default_event_handlers = {}

    def __init__(self):
        EventDispatcher.__init__(self)
        assert isinstance(self._event_stack, tuple)
        self._event_stack = [self.default_event_handlers]

        # list of elements that have responded to an on_element_enter event
        self.entered_elements = []

    @classmethod
    def set_default_handler(cls, name, selector, handler):
        '''Inspect handler for a selector and apply to the primary-set.
        If the handler has no selector, it is assumed to have a universal
        selector.
        '''
        if name not in cls.default_event_handlers:
            cls.default_event_handlers[name] = RuleSet()
        ruleset = cls.default_event_handlers[name]
        ruleset.add_rule(Rule(selector, handler))

    def select(self, rule, event_name=None):
        # XXX assume passed an element with an id to select on
        if not isinstance(rule, str):
            rule = '#' + rule.id

        def decorate(func):
            func.selectors = [Selector.from_string(r.strip())
                for r in rule.split(',')]
            if event_name is not None:
                func.event_name = event_name
            self.push_handlers(func)
            return func
        return decorate

    def set_handlers(self, *args, **kwargs):
        '''Attach one or more event handlers to the top level of the handler
        stack.
        
        See `push_handlers` for the accepted argument types.
        '''
        # Create event stack if necessary
        if type(self._event_stack) is tuple:
            self._event_stack = [{}]

        for object in args:
            if inspect.isroutine(object):
                # Single magically named function
                name = getattr(object, 'event_name', object.__name__)
                if name not in self.event_types:
                    raise EventException('Unknown event "%s"' % name)
                self.set_handler(name, object)
            else:
                # Single instance with magically named methods
                for name, handler in inspect.getmembers(object):
                    name = getattr(handler, 'event_name', name)
                    if name in self.event_types:
                        self.set_handler(name, handler)
        for name, handler in kwargs.items():
            # Function for handling given event (no magic)
            if name not in self.event_types:
                raise EventException('Unknown event "%s"' % name)
            self.set_handler(name, handler)

    def set_handler(self, name, handler):
        '''Inspect handler for a selector and apply to the primary-set.
        If the handler has no selector, it is assumed to have a universal
        selector.
        '''
        if name not in self._event_stack[0]:
            self._event_stack[0][name] = RuleSet()
        ruleset = self._event_stack[0][name]
        #if not hasattr(handler, 'selector'):
            #handler.selector = universal_selector
        for selector in handler.selectors:
            ruleset.add_rule(Rule(selector, handler))

    def dispatch_event(self, element, event_type, *args, **kw):
        update_active=kw.get('update_active', True)
        propogate=kw.get('propogate', True)
        if element.isEnabled():
            for frame in self._event_stack:
                ruleset = frame.get(event_type, None)
                if ruleset:
                    rules = ruleset.get_matching_rules(element)
                    for rule in rules:
                        handler = rule.declaration_set
                        try:
                            ret = handler(element, *args)
                        except TypeError, message:
                            print 'ERROR CALLING  %r (%r, *%r)]'%(handler,
                                element, args)
                            raise
                        if ret != EVENT_UNHANDLED:
                            # update the currently-active element
                            if update_active:
                                self.active_element = element
                            return True

        # not handled, so pass the event up to parent element
        if propogate and element.parent is not None:
            return self.dispatch_event(element.parent, event_type, *args, **kw)

    # NOW THE EVENT HANDLERS
    active_element = None
    is_dragging_element = False
    mouse_press_element = None
    drag_over_element = None
    cumulative_drag = (0, 0)
    focused_element = None

    _rects = None
    def setDirty(self):
        '''Indicate that one or more of the gui's children have changed
        size and a new set of collision rects is needed.
        '''
        self._rects = None

    def setFocus(self, element):
        '''Set the indicated element to be the focus of keyboard input.

        All future `on_text`, `on_text_motion` and `on_text_motion_select`
        events will be passed to the element.
        '''
        # gain focus first so some elements are able to detect whether their
        # child has been focused
        if element is not None and self.focused_element is not element:
            ae = self.active_element
            self.dispatch_event(element, 'on_gain_focus')
            if self.active_element is not ae:
                # focus was caught by some parent element
                element = self.active_element
            else:
                # focus was uncaught - stay with the element targetted
                self.active_element = element

        if (self.focused_element is not None and
                self.focused_element is not element):
            self.dispatch_event(self.focused_element, 'on_lose_focus',
                update_active=False)

        self.focused_element = element

    def determineHit(self, x, y, exclude=None):
        '''Determine which element is at the absolute (x, y) position.

        "exclude" allows us to ignore a single element (eg. an element
        under the cursor being dragged - we wish to know which element is
        under *that)
        '''
        for o, (ox, oy, oz, sx, sy, clip) in self.getRects(exclude):
            ox += clip.x
            oy += clip.y
            if x < ox: continue
            if y < oy: continue
            if x > ox + clip.width: continue
            if y > oy + clip.height: continue
            return o
        return None


    def on_mouse_motion(self, x, y, dx, dy):
        '''Determine what element(s) the mouse is positioned over and
        generate on_element_enter and on_element_leave events. Additionally
        generate a new on_mouse_motion event for the element under the
        mouse.
        '''
        element = self.determineHit(x, y)

        if self.debug_display is not None:
            self.debug_display.setText(repr(element))

        # see which elements (starting with the one under the mouse and
        # moving up the parentage) care about an on_element_enter event
        over = []
        e = element
        active_element = self.active_element
        while e:
            if not e.isEnabled():
                e = e.parent
                continue
            if e in self.entered_elements:
                over.append(e)
                e = e.parent
                continue
            if self.dispatch_event(e, 'on_element_enter', x, y,
                    propogate=False):
                over.append(e)
            e = e.parent

        # right, now "leave" any elements that aren't in "over" any
        # more
        for e in self.entered_elements:
            if e not in over:
                self.dispatch_event(e, 'on_element_leave', x, y)

        #if mouse stable (not moving)? and 1 second has passed
        #    element.on_element_hover(x, y)

        self.entered_elements = over

        if element is not None:
            self.dispatch_event(element, 'on_mouse_motion', x, y, dx, dy)

        # restore old active element
        self.active_element = active_element
        return EVENT_HANDLED

    def on_mouse_enter(self, x, y):
        '''Translate this into an on_mouse_motion event.
        '''
        return self.on_mouse_motion(x, y, 0, 0)

    def on_mouse_leave(self, x, y):
        '''Translate this into an on_element_leave for all
        on_element_enter'ed elements.
        '''
        # leave all entered elements
        for e in self.entered_elements:
            self.dispatch_event(e, 'on_element_leave', x, y)
        self.entered_elements = []

        # cancel current drag
        if self.is_dragging_element:
            # XXX button and modifiers...
            self.dispatch_event(self.mouse_press_element,
                'on_drag_complete', x, y, 0, 0, False)
        return EVENT_HANDLED

    def on_mouse_press(self, x, y, button, modifiers):
        '''Pass this event on to the element underneath the mouse.
        Additionally, switch keyboard focus to this element through
        `self.setFocus(element)`

        The element will be registered as potentially interesting for
        generating future `on_click` and `on_drag` events.
        '''
        element = self.determineHit(x, y)
        if element is None: return EVENT_UNHANDLED
        if not element.is_enabled: return EVENT_UNHANDLED

        # remember the pressed element so that we can:
        # 1. pass it mouse drag events even if the mouse moves off its hit area
        # 2. TODO pass it a "lost focus" event?
        self.active_element = element
        self.mouse_press_element = element
        self.is_dragging_element = False
        self.cumulative_drag = (0, 0)

        #print 'PRESS, active=', element

        # switch focus
        self.setFocus(element)

        return self.dispatch_event(element, 'on_mouse_press', x, y, button,
            modifiers)

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        '''Translate this event into a number of events:
        
        If the mouse button was pressed while over an element we attempt to
        pass an `on_mouse_drag` event to that element. If that event is
        handled and the handler returns EVENT_HANDLED then [XXX we additionally
        generate an `on_mouse_release` event (once per drag) and XXX] this
        handler returns.
        
        If the mouse button was pressed while over an element we attempt to
        pass an `on_drag` event to that element. If that event is
        handled and the handler returns EVENT_HANDLED [XXX then we additionally
        generate an `on_mouse_release` event (once per drag). XXX] We then
        attempt to pass on_drag_enter and on_drag_leave events on the
        element *under* the element being dragged.

        If no event handling was invoked above then we generate an
        `on_mouse_drag` event for the element underneath the mouse pointer.
        '''
#        print 'DRAG, active=', self.active_element
#        print '..... press=', self.mouse_press_element

        if self.mouse_press_element is not None:

            # check drag threshold
            cdx, cdy = self.cumulative_drag
            cdx += abs(dx); cdy += abs(dy)
            self.cumulative_drag = (cdx, cdy)
            if cdx + cdy < 4:
                # less than 4 pixels, don't drag just yet
#                print 'NOT ENOUGH DRAG', cdx + cdy
                return EVENT_UNHANDLED

            # see if the previously-pressed element wants...

            # an on_mouse_drag event
            handled = self.dispatch_event(self.mouse_press_element,
                'on_mouse_drag', x, y, dx, dy, buttons, modifiers)
            if handled == EVENT_HANDLED:
#                print 'MOUSE_DRAG HANDLED', self.mouse_press_element
#                if self.mouse_press_element is not None:
#                    self.dispatch_event(self.mouse_press_element,
#                        'on_mouse_release', x, y, buttons, modifiers,
#                        update_active=False)
#                    self.mouse_press_element = None
                return EVENT_HANDLED

            # or an on_drag event
            handled = self.dispatch_event(self.mouse_press_element, 'on_drag',
                x, y, dx, dy, buttons, modifiers)
            if handled == EVENT_HANDLED:
#                print 'DRAG HANDLED', self.mouse_press_element
#                if self.mouse_press_element is not None:
#                    self.dispatch_event(self.mouse_press_element,
#                        'on_mouse_release', x, y, buttons, modifiers,
#                        update_active=False)
#                    self.mouse_press_element == None

                # tell the element we've dragged the active element over
                element = self.determineHit(x, y,
                    exclude=self.mouse_press_element)
                if element is not self.drag_over_element:
                    if self.drag_over_element is not None:
                        self.dispatch_event(self.drag_over_element,
                            'on_drag_leave', x, y, self.active_element,
                            update_active=False)
                if element is not None and element.is_enabled:
                    self.dispatch_event(element, 'on_drag_enter', x, y,
                        self.active_element, update_active=False)
                self.drag_over_element = element

                self.is_dragging_element = True
                return EVENT_HANDLED

        # regular event pass-through
        element = self.determineHit(x, y)
        if element is None: return EVENT_UNHANDLED
        if not element.is_enabled:
            self.active_element = None
            return EVENT_UNHANDLED
        self.is_dragging_element = False
        return self.dispatch_event(element, 'on_mouse_drag', x, y, dx, dy,
            buttons, modifiers)

    _last_click = 0
    def on_mouse_release(self, x, y, button, modifiers):
        self.cumulative_drag = (0, 0)
        if self.is_dragging_element:
            # the on_drop check will most likely alter the active element
            dragged = self.mouse_press_element
            element = self.determineHit(x, y, exclude=dragged)

            # see if the element underneath wants the dragged element
            if element is not None and element.is_enabled:
                ok = self.dispatch_event(element, 'on_drop', x, y, button,
                    modifiers, dragged) == EVENT_HANDLED
                new_active_element = element
            else:
                ok = False
                new_active_element = None

            # now tell the dragged element what's going on
            handled = self.dispatch_event(dragged,
                'on_drag_complete', x, y, button, modifiers, ok)

            # clear state - we're done
            self.active_element = new_active_element
            self.is_dragging_element = False
            return handled

        # XXX do we want to pass the release event to this element?
        # (most user-interfaces don't pass a "click" event to a button that's
        # no longer under the mouse.)
        self.active_element = None

        # regular mouse press/release click
        element = self.determineHit(x, y)
        if element is None: return EVENT_UNHANDLED
        if not element.is_enabled:
            return EVENT_UNHANDLED

        handled =  self.dispatch_event(element, 'on_mouse_release', x, y,
            button, modifiers)
        if handled == EVENT_HANDLED:
            return EVENT_HANDLED

        now = time.time()
        if now - self._last_click < .25:
            self._click_count += 1
        else:
            self._click_count = 1
        self._last_click = now

        if element is self.mouse_press_element:
            return self.dispatch_event(element, 'on_click', x, y, button,
                modifiers, self._click_count)
        return EVENT_UNHANDLED

    def on_mouse_scroll(self, x, y, dx, dy):
        element = self.determineHit(x, y)
        if element is None: return EVENT_UNHANDLED
        return self.dispatch_event(element, 'on_mouse_scroll', x, y, dx, dy)

    # the following are special -- they will be sent to the currently-focused
    # element rather than being dispatched
    def on_key_press(self, symbol, modifiers):
        handled = EVENT_UNHANDLED
        if self.focused_element is not None:
            handled = self.dispatch_event(self.focused_element,
                'on_key_press', symbol, modifiers)
        if handled == EVENT_UNHANDLED and symbol == key.TAB:
            if modifiers & key.MOD_SHIFT:
                self.focusNextElement(-1)
            else:
                self.focusNextElement()
        return handled

    def on_text(self, text):
        if self.focused_element is None: return
        return self.dispatch_event(self.focused_element, 'on_text', text)

    def on_text_motion(self, motion):
        if self.focused_element is None: return
        return self.dispatch_event(self.focused_element, 'on_text_motion',
            motion)

    def on_text_motion_select(self, motion):
        if self.focused_element is None: return
        return self.dispatch_event(self.focused_element,
            'on_text_motion_select', motion)


# EVENTS IN and OUT
GUIEventDispatcher.register_event_type('on_mouse_motion')
GUIEventDispatcher.register_event_type('on_mouse_press')
GUIEventDispatcher.register_event_type('on_mouse_release')
GUIEventDispatcher.register_event_type('on_mouse_enter')
GUIEventDispatcher.register_event_type('on_mouse_leave')
GUIEventDispatcher.register_event_type('on_mouse_drag')
GUIEventDispatcher.register_event_type('on_mouse_scroll')

GUIEventDispatcher.register_event_type('on_key_press')
GUIEventDispatcher.register_event_type('on_text')
GUIEventDispatcher.register_event_type('on_text_motion')
GUIEventDispatcher.register_event_type('on_text_motion_select')

# EVENTS OUT
GUIEventDispatcher.register_event_type('on_change')
GUIEventDispatcher.register_event_type('on_click')
GUIEventDispatcher.register_event_type('on_drag')
GUIEventDispatcher.register_event_type('on_drag_enter')
GUIEventDispatcher.register_event_type('on_drag_leave')
GUIEventDispatcher.register_event_type('on_drag_complete')
GUIEventDispatcher.register_event_type('on_drop')
GUIEventDispatcher.register_event_type('on_element_enter')
GUIEventDispatcher.register_event_type('on_element_leave')
GUIEventDispatcher.register_event_type('on_gain_focus')
GUIEventDispatcher.register_event_type('on_lose_focus')
        

def select(rule, event_name=None):
    # XXX assume passed an element with an id to select on
    if not isinstance(rule, str):
        rule = '#' + rule.id

    def decorate(func):
        func.selectors = [Selector.from_string(r.strip())
            for r in rule.split(',')]
        if event_name is not None:
            func.event_name = event_name
        return func
    return decorate


def default(rule, event_name=None):
    def decorate(func):
        name = event_name or func.__name__
        if name not in GUIEventDispatcher.event_types:
            raise EventException('Unknown event "%s"' % name)
        for r in rule.split(','):
            selector = Selector.from_string(r.strip())
            GUIEventDispatcher.set_default_handler(name, selector, func)
        return func
    return decorate


universal_selector = Selector(SimpleSelector(None, None, (), (), ()), ())

