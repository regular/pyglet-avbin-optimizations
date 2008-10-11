#!/usr/bin/env python

'''
'''

__docformat__ = 'restructuredtext'
__version__ = '$Id: $'

import sys
import threading
import Queue

from pyglet import app
from pyglet import clock
from pyglet import event

_is_epydoc = hasattr(sys, 'is_epydoc') and sys.is_epydoc

class PlatformEventLoop(object):
    '''
    :since: pyglet 1.2
    '''
    def __init__(self):
        self._event_queue = Queue.Queue()
        self._is_running = threading.Event()
        self._is_running.clear()

    def is_running(self):  
        '''Return True if the event loop is currently processing, or False
        if it is blocked or not activated.

        :rtype: bool
        '''
        return self._is_running.is_set()

    def post_event(self, dispatcher, event, *args):
        '''Post an event into the main application thread.

        The event is queued internally until the `run` method's thread
        is able to dispatch the event.  This method can be safely called
        from any thread.

        If the method is called from the `run` method's thread (for example,
        from within an event handler), the event may be dispatched within
        the same runloop iteration or the next one; the choice is
        nondeterministic.

        :Parameters:
            `dispatcher` : EventDispatcher
                Dispatcher to process the event.
            `event` : str
                Event name.
            `args` : sequence
                Arguments to pass to the event handlers.

        '''
        self._event_queue.put((dispatcher, event, args))
        self.notify()

    def dispatch_posted_events(self):
        '''Immediately dispatch all pending events.

        Normally this is called automatically by the runloop iteration.
        '''
        while True:
            try:
                dispatcher, event, args = self._event_queue.get(False)
            except Queue.Empty:
                break

            dispatcher.dispatch_event(event, *args)

    def notify(self):
        '''Notify the event loop that something needs processing.

        If the event loop is blocked, it will unblock and perform an iteration
        immediately.  If the event loop is running, another iteration is
        scheduled for immediate execution afterwards.
        '''
        raise NotImplementedError('abstract')

    def start(self):
        pass

    def step(self, timeout=None):
        raise NotImplementedError('abstract')

    def set_timer(self, func, interval):
        raise NotImplementedError('abstract')

    def stop(self):
        pass

class EventLoop(event.EventDispatcher):
    '''The main run loop of the application.

    Calling `run` begins the application event loop, which processes
    operating system events, calls `pyglet.clock.tick` to call scheduled
    functions and calls `pyglet.window.Window.on_draw` and
    `pyglet.window.Window.flip` to update window contents.

    Applications can subclass `EventLoop` and override certain methods
    to integrate another framework's run loop, or to customise processing
    in some other way.  You should not in general override `run`, as
    this method contains platform-specific code that ensures the application
    remains responsive to the user while keeping CPU usage to a minimum.
    '''

    _has_exit_condition = None
    _has_exit = False

    def __init__(self):
        self._has_exit_condition = threading.Condition()

    def run(self):
        '''Begin processing events, scheduled functions and window updates.

        This method returns when `has_exit` is set to True.

        Developers are discouraged from overriding this method, as the
        implementation is platform-specific.
        '''
        self._legacy_setup()

        platform_event_loop = app.platform_event_loop
        platform_event_loop.start()
        self.dispatch_event('on_enter')

        while not self.has_exit:
            timeout = self.idle()
            platform_event_loop.step(timeout)
            
        self.dispatch_event('on_exit')
        platform_event_loop.stop()

    def _legacy_setup(self):
        # Disable event queuing for dispatch_events
        from pyglet.window import Window
        Window._enable_event_queue = False
        
        # Dispatch pending events
        for window in app.windows:
            window.switch_to()
            window.dispatch_pending_events()

    def enter_blocking(self):
        '''Called by pyglet internal processes when the operating system
        is about to block due to a user interaction.  For example, this
        is common when the user begins resizing or moving a window.

        This method provides the event loop with an opportunity to set up
        an OS timer on the platform event loop, which will continue to
        be invoked during the blocking operation.

        The default implementation ensures that `idle` continues to be called
        as documented.

        :since: pyglet 1.2
        '''
        timeout = self.idle()
        app.platform_event_loop.set_timer(self._blocking_timer, timeout)

    def exit_blocking(self):
        '''Called by pyglet internal processes when the blocking operation
        completes.  See `enter_blocking`.
        '''
        app.platform_event_loop.set_timer(None, None)

    def _blocking_timer(self):
        timeout = self.idle()
        app.platform_event_loop.set_timer(self._blocking_timer, timeout)

    def idle(self):
        '''Called during each iteration of the event loop.

        The method is called immediately after any window events (i.e., after
        any user input).  The method can return a duration after which
        the idle method will be called again.  The method may be called
        earlier if the user creates more input events.  The method
        can return `None` to only wait for user events.

        For example, return ``1.0`` to have the idle method called every
        second, or immediately after any user events.

        The default implementation dispatches the
        `pyglet.window.Window.on_draw` event for all windows and uses
        `pyglet.clock.tick` and `pyglet.clock.get_sleep_time` on the default
        clock to determine the return value.

        This method should be overridden by advanced users only.  To have
        code execute at regular intervals, use the
        `pyglet.clock.schedule` methods.

        :rtype: float
        :return: The number of seconds before the idle method should
            be called again, or `None` to block for user input.
        '''
        dt = clock.tick(True)

        # Redraw all windows
        for window in app.windows:
            if window.invalid:
                window.switch_to()
                window.dispatch_event('on_draw')
                window.flip()

        # Update timout
        return clock.get_sleep_time(True)

    def _get_has_exit(self):
        self._has_exit_condition.acquire()
        result = self._has_exit
        self._has_exit_condition.release()
        return result

    def _set_has_exit(self, value):
        self._has_exit_condition.acquire()
        self._has_exit = value
        self._has_exit_condition.notify()
        self._has_exit_condition.release()

    has_exit = property(_get_has_exit, _set_has_exit,
                        doc='''Flag indicating if the event loop will exit in
    the next iteration.  When set, all waiting threads are interrupted (see
    `sleep`).
    
    Thread-safe since pyglet 1.2.

    :see: `exit`
    :type: bool
    ''')

    def exit(self):
        '''Safely exit the event loop at the end of the current iteration.

        This method is a thread-safe equivalent for for setting `has_exit` to
        ``True``.  All waiting threads will be interrupted (see
        `sleep`).
        '''
        self._set_has_exit(True)
        app.platform_event_loop.notify()

    def sleep(self, timeout):
        '''Wait for some amount of time, or until the `has_exit` flag is
        set or `exit` is called.

        This method is thread-safe.

        :Parameters:
            `timeout` : float
                Time to wait, in seconds.

        :since: pyglet 1.2

        :rtype: bool
        :return: ``True`` if the `has_exit` flag is now set, otherwise
        ``False``.
        '''
        self._has_exit_condition.acquire()
        self._has_exit_condition.wait(timeout)
        result = self._has_exit
        self._has_exit_condition.release()
        return result

    def on_window_close(self, window):
        '''Default window close handler.'''
        if not app.windows:
            self.exit()

    if _is_epydoc:
        def on_window_close(window):
            '''A window was closed.

            This event is dispatched when a window is closed.  It is not
            dispatched if the window's close button was pressed but the
            window did not close.

            The default handler calls `exit` if no more windows are open.  You
            can override this handler to base your application exit on some
            other policy.

            :event:
            '''

        def on_enter():
            '''The event loop is about to begin.

            This is dispatched when the event loop is prepared to enter
            the main run loop, and represents the last chance for an 
            application to initialise itself.

            :event:
            '''

        def on_exit():
            '''The event loop is about to exit.

            After dispatching this event, the `run` method returns (the
            application may not actually exit if you have more code
            following the `run` invocation).

            :event:
            '''

EventLoop.register_event_type('on_window_close')
EventLoop.register_event_type('on_enter')
EventLoop.register_event_type('on_exit')
