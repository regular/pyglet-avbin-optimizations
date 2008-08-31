#!/usr/bin/env python

'''
'''

__docformat__ = 'restructuredtext'
__version__ = '$Id: $'

from pyglet import app
from base import Display, Screen, Canvas

from pyglet.libs.darwin import *

class CarbonDisplay(Display):
    # TODO: CarbonDisplay could be per display device, which would make
    # reporting of screens and available configs more accurate.  The number of
    # Macs with more than one video card is probably small, though.
    def __init__(self):
        super(CarbonDisplay, self).__init__()

        import MacOS
        if not MacOS.WMAvailable():
            raise app.AppException('Window manager is not available.  ' \
                                   'Ensure you run "pythonw", not "python"')

        self._install_application_event_handlers()
        
    def get_screens(self):
        count = CGDisplayCount()
        carbon.CGGetActiveDisplayList(0, None, byref(count))
        displays = (CGDirectDisplayID * count.value)()
        carbon.CGGetActiveDisplayList(count.value, displays, byref(count))
        return [CarbonScreen(self, id) for id in displays]

    def _install_application_event_handlers(self):
        self._carbon_event_handlers = []
        self._carbon_event_handler_refs = []

        target = carbon.GetApplicationEventTarget()

        # TODO something with a metaclass or hacky like CarbonWindow
        # to make this list extensible
        handlers = [
            (self._on_mouse_down, kEventClassMouse, kEventMouseDown),
            (self._on_apple_event, kEventClassAppleEvent, kEventAppleEvent),
            (self._on_command, kEventClassCommand, kEventProcessCommand),
        ]

        ae_handlers = [
            (self._on_ae_quit, kCoreEventClass, kAEQuitApplication),
        ]

        # Install the application-wide handlers
        for method, cls, event in handlers:
            proc = EventHandlerProcPtr(method)
            self._carbon_event_handlers.append(proc)
            upp = carbon.NewEventHandlerUPP(proc)
            types = EventTypeSpec()
            types.eventClass = cls
            types.eventKind = event
            handler_ref = EventHandlerRef()
            carbon.InstallEventHandler(
                target,
                upp,
                1,
                byref(types),
                c_void_p(),
                byref(handler_ref))
            self._carbon_event_handler_refs.append(handler_ref)

        # Install Apple event handlers
        for method, cls, event in ae_handlers:
            proc = EventHandlerProcPtr(method)
            self._carbon_event_handlers.append(proc)
            upp = carbon.NewAEEventHandlerUPP(proc)
            carbon.AEInstallEventHandler(
                cls,
                event,
                upp,
                0,
                False)

    def _on_command(self, next_handler, ev, data):
        command = HICommand()
        carbon.GetEventParameter(ev, kEventParamDirectObject,
            typeHICommand, c_void_p(), sizeof(command), c_void_p(),
            byref(command))

        if command.commandID == kHICommandQuit:
            self._on_quit()

        return noErr

    def _on_mouse_down(self, next_handler, ev, data):
        # Check for menubar hit
        position = Point()
        carbon.GetEventParameter(ev, kEventParamMouseLocation,
            typeQDPoint, c_void_p(), sizeof(position), c_void_p(),
            byref(position))
        if carbon.FindWindow(position, None) == inMenuBar:
            # Mouse down in menu bar.  MenuSelect() takes care of all
            # menu tracking and blocks until the menu is dismissed.
            # Use command events to handle actual menu item invokations.

            # This function blocks, so tell the event loop it needs to install
            # a timer.
            app.event_loop._enter_blocking()
            carbon.MenuSelect(position)
            app.event_loop._exit_blocking()

            # Menu selection has now returned.  Remove highlight from the
            # menubar.
            carbon.HiliteMenu(0)

        carbon.CallNextEventHandler(next_handler, ev)
        return noErr

    def _on_apple_event(self, next_handler, ev, data):
        # Somewhat involved way of redispatching Apple event contained
        # within a Carbon event, described in
        # http://developer.apple.com/documentation/AppleScript/
        #  Conceptual/AppleEvents/dispatch_aes_aepg/chapter_4_section_3.html

        release = False
        if carbon.IsEventInQueue(carbon.GetMainEventQueue(), ev):
            carbon.RetainEvent(ev)
            release = True
            carbon.RemoveEventFromQueue(carbon.GetMainEventQueue(), ev)

        ev_record = EventRecord()
        carbon.ConvertEventRefToEventRecord(ev, byref(ev_record))
        carbon.AEProcessAppleEvent(byref(ev_record))

        if release:
            carbon.ReleaseEvent(ev)
        
        return noErr

    def _on_ae_quit(self, ae, reply, refcon):
        self._on_quit()
        return noErr

    def _on_quit(self):
        '''Called when the user tries to quit the application.

        This is not an actual event handler, it is called in response
        to Command+Q, the Quit menu item, and the Dock context menu's Quit
        item.

        The default implementation calls `EventLoop.exit` on
        `pyglet.app.event_loop`.
        '''
        app.event_loop.exit()

class CarbonScreen(Screen):
    def __init__(self, display, id):
        self.display = display
        rect = carbon.CGDisplayBounds(id)
        super(CarbonScreen, self).__init__(display,
            int(rect.origin.x), int(rect.origin.y),
            int(rect.size.width), int(rect.size.height))
        self.id = id

        mode = carbon.CGDisplayCurrentMode(id)
        kCGDisplayRefreshRate = create_cfstring('RefreshRate')
        number = carbon.CFDictionaryGetValue(mode, kCGDisplayRefreshRate)
        refresh = c_long()
        kCFNumberLongType = 10
        carbon.CFNumberGetValue(number, kCFNumberLongType, byref(refresh))
        self._refresh_rate = refresh.value

    def get_matching_configs(self, template):
        canvas = CarbonCanvas(self.display, self, None)
        configs = template.match(canvas)
        # XXX deprecate
        for config in configs:
            config.screen = self
        return configs
 
class CarbonCanvas(Canvas):
    def __init__(self, display, screen, drawable):
        super(CarbonCanvas, self).__init__(display)
        self.screen = screen
        self.drawable = drawable
