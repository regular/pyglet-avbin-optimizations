#!/usr/bin/python
# $Id:$

import ctypes
import math
import sys
import threading
import time

import pyglet
_debug = pyglet.options['debug_media']

import mt_media

import lib_dsound as lib
from pyglet.window.win32 import _user32, _kernel32

class DirectSoundException(mt_media.MediaException):
    pass

def _db(gain):
    '''Convert linear gain in range [0.0, 1.0] to 100ths of dB.'''
    if gain <= 0:
        return -10000
    return max(-10000, min(int(1000 * math.log(min(gain, 1))), 0))

class DirectSoundWorker(mt_media.MediaThread):
    _min_write_size = 9600

    # Time to wait if there are players, but they're all full.
    _nap_time = 0.05

    # Time to wait if there are no players.
    _sleep_time = None

    def __init__(self, target=None):
        super(DirectSoundWorker, self).__init__(target)
        self.players = set()

    def run(self):
        while True:
            # This is a big lock, but ensures a player is not deleted while
            # we're processing it -- this saves on extra checks in the
            # player's methods that would otherwise have to check that it's
            # still alive.
            self.condition.acquire()

            if self.stopped:
                self.condition.release()
                break
            sleep_time = -1

            if self.players:
                player = None
                write_size = 0
                for p in self.players:
                    s = p.get_write_size()
                    if s > write_size:
                        player = p
                        write_size = s

                if write_size > self._min_write_size:
                    player.refill(write_size)
                else:
                    sleep_time = self._nap_time
            else:
                sleep_time = self._sleep_time

            self.condition.release()

            if sleep_time != -1:
                self.sleep(sleep_time)

    def add(self, player):
        self.condition.acquire()
        self.players.add(player)
        self.condition.notify()
        self.condition.release()

    def remove(self, player):
        self.condition.acquire()
        self.players.remove(player)
        self.condition.notify()
        self.condition.release()

class DirectSoundAudioPlayer(mt_media.AbstractAudioPlayer):
    # How many bytes the ring buffer should be
    _buffer_size = 44800 * 1

    # Need to cache these because pyglet API allows update separately, but
    # DSound requires both to be set at once.
    _cone_inner_angle = 360
    _cone_outer_angle = 360

    def __init__(self, source_group, player):
        super(DirectSoundAudioPlayer, self).__init__(source_group, player)

        # Locking strategy:
        # All DirectSound calls should be locked.  All instance vars relating
        # to buffering/filling/time/events should be locked (used by both
        # application and worker thread).  Other instance vars (consts and
        # 3d vars) do not need to be locked.
        self._lock = threading.RLock()

        # Desired play state (may be actually paused due to underrun -- not
        # implemented yet).
        self._playing = False

        # Up to one audio data may be buffered if too much data was received
        # from the source that could not be written immediately into the
        # buffer.  See refill().
        self._next_audio_data = None

        # Last known timestamp, or paused timestamp (not yet implemented).
        self._timestamp = 0.0

        # Theoretical write and play cursors for an infinite buffer.  play
        # cursor is always <= write cursor (when equal, underrun is
        # happening).
        self._write_cursor = 0
        self._play_cursor = 0

        # Cursor position of end of data.  Silence is written after
        # eos for one buffer size.
        self._eos_cursor = None

        # Indexes into DSound circular buffer.  Complications ensue wrt each
        # other to avoid writing over the play cursor.  See get_write_size and
        # write().
        self._play_cursor_ring = 0
        self._write_cursor_ring = 0

        # List of (play_cursor, MediaEvent), in sort order
        self._events = []

        audio_format = source_group.audio_format

        wfx = lib.WAVEFORMATEX()
        wfx.wFormatTag = lib.WAVE_FORMAT_PCM
        wfx.nChannels = audio_format.channels
        wfx.nSamplesPerSec = audio_format.sample_rate
        wfx.wBitsPerSample = audio_format.sample_size
        wfx.nBlockAlign = wfx.wBitsPerSample * wfx.nChannels // 8
        wfx.nAvgBytesPerSec = wfx.nSamplesPerSec * wfx.nBlockAlign

        dsbdesc = lib.DSBUFFERDESC()
        dsbdesc.dwSize = ctypes.sizeof(dsbdesc)
        dsbdesc.dwFlags = (lib.DSBCAPS_GLOBALFOCUS | 
                           lib.DSBCAPS_GETCURRENTPOSITION2 |
                           lib.DSBCAPS_CTRLFREQUENCY |
                           lib.DSBCAPS_CTRLVOLUME)
        if audio_format.channels == 1:
            dsbdesc.dwFlags |= lib.DSBCAPS_CTRL3D
        dsbdesc.dwBufferBytes = self._buffer_size
        dsbdesc.lpwfxFormat = ctypes.pointer(wfx)

        # DSound buffer
        self._buffer = lib.IDirectSoundBuffer()
        driver._dsound.CreateSoundBuffer(dsbdesc, 
                                         ctypes.byref(self._buffer), 
                                         None)

        if audio_format.channels == 1:
            self._buffer3d = lib.IDirectSound3DBuffer()
            self._buffer.QueryInterface(lib.IID_IDirectSound3DBuffer, 
                                        ctypes.byref(self._buffer3d))
        else:
            self._buffer3d = None
        
        self._buffer.SetCurrentPosition(0)

        self.refill(self._buffer_size)
            
    def __del__(self):
        try:
            self.delete()
        except:
            pass

    def delete(self):
        if driver and driver.worker:
            driver.worker.remove(self)

        self.lock()

        self._buffer.Stop()
        self._buffer.Release()
        self._buffer = None
        if self._buffer3d:
            self._buffer3d.Release()
            self._buffer3d = None

        self.unlock()

    def lock(self):
        self._lock.acquire()

    def unlock(self):
        self._lock.release()
        
    def play(self):
        self.lock()
        if not self._playing:
            self._playing = True

            self._buffer.Play(0, 0, lib.DSBPLAY_LOOPING)
            driver.worker.add(self)
        self.unlock()

    def stop(self):
        self.lock()
        if self._playing:
            self._playing = False

            self._buffer.Stop()
            driver.worker.remove(self)
        self.unlock()

    def clear(self):
        self.lock()
        self._write_cursor_ring = 0
        self._buffer.SetCurrentPosition(0)
        self._write_cursor = 0
        self.unlock()

    def refill(self, write_size):
        self.lock()
        while write_size > 0:
            if _debug:
                print 'refill, write_size =', write_size
            # Get next audio packet (or remains of last one)
            if self._next_audio_data:
                audio_data = self._next_audio_data
                self._next_audio_data = None
            else:
                audio_data = self.source_group.get_audio_data(write_size)

            # Write it, or silence if there are no more packets
            if audio_data:
                for event in audio_data.events:
                    event_cursor = self._write_cursor + event.timestamp * \
                        self.source_group.audio_format.bytes_per_second
                    self._events.append((event_cursor, event))
                if _debug:
                    print 'write', audio_data.length
                length = min(write_size, audio_data.length)
                self.write(audio_data, length)
                if audio_data.length:
                    self._next_audio_data = audio_data
                write_size -= length
            else:
                if self._eos_cursor is None:
                    self._eos_cursor = self._write_cursor
                    self._events.append(
                        (self._eos_cursor, 
                         mt_media.MediaEvent(0, 'on_eos')))
                    self._events.append(
                        (self._eos_cursor, 
                         mt_media.MediaEvent(0, 'on_source_group_eos')))
                    self._events.sort()
                if self._write_cursor > self._eos_cursor + self._buffer_size:
                    self.stop()
                else:
                    self.write(None, write_size)
                write_size = 0

        self.unlock()

    def update_play_cursor(self):
        self.lock()
        play_cursor_ring = lib.DWORD()
        self._buffer.GetCurrentPosition(play_cursor_ring, None)
        if play_cursor_ring.value < self._play_cursor_ring:
            # Wrapped around
            self._play_cursor += self._buffer_size - self._play_cursor_ring
            self._play_cursor_ring = 0
        self._play_cursor += play_cursor_ring.value - self._play_cursor_ring
        self._play_cursor_ring = play_cursor_ring.value

        # Dispatch pending events
        pending_events = []
        while self._events and self._events[0][0] <= self._play_cursor:
            _, event = self._events.pop(0)
            pending_events.append(event)
        if _debug:
            print 'Dispatching pending events:', pending_events
            print 'Remaining events:', self._events

        self.unlock()

        for event in pending_events:
            event._sync_dispatch_to_player(self.player)
            
    def get_write_size(self):
        self.update_play_cursor()

        self.lock()
        play_cursor = self._play_cursor
        write_cursor = self._write_cursor
        self.unlock()

        return self._buffer_size - (write_cursor - play_cursor)

    def write(self, audio_data, length):
        # Pass audio_data=None to write silence
        if length == 0:
            return 0

        self.lock()

        p1 = ctypes.c_void_p()
        l1 = lib.DWORD()
        p2 = ctypes.c_void_p()
        l2 = lib.DWORD()
        self._buffer.Lock(self._write_cursor_ring, length, 
            ctypes.byref(p1), l1, ctypes.byref(p2), l2, 0)
        assert length == l1.value + l2.value

        if audio_data:
            ctypes.memmove(p1, audio_data.data, l1.value)
            audio_data.consume(l1.value, self.source_group.audio_format)
            if l2.value:
                ctypes.memmove(p2, audio_data.data, l2.value)
                audio_data.consume(l2.value, self.source_group.audio_format)
        else:
            ctypes.memset(p1, 0, l1.value)
            if l2.value:
                ctypes.memset(p2, 0, l2.value)
        self._buffer.Unlock(p1, l1, p2, l2)

        self._write_cursor += length
        self._write_cursor_ring += length
        self._write_cursor_ring %= self._buffer_size
        self.unlock()

    def get_time(self):
        # Will be accurate to within driver.worker._nap_time secs (0.02).
        # XXX Could provide another method that gets a more accurate time, at
        # more expense.
        self.lock()
        t = self._timestamp
        self.unlock()
        return t
        
    def set_volume(self, volume):
        volume = _db(volume)
        self.lock()
        self._buffer.SetVolume(volume)
        self.unlock()

    def set_position(self, position):
        if self._buffer3d:
            x, y, z = position
            self.lock()
            self._buffer3d.SetPosition(x, y, -z, lib.DS3D_IMMEDIATE)
            self.unlock()

    def set_min_distance(self, min_distance):
        if self._buffer3d:
            self.lock()
            self._buffer3d.SetMinDistance(min_distance, lib.DS3D_IMMEDIATE)
            self.unlock()

    def set_max_distance(self, max_distance):
        if self._buffer3d:
            self.lock()
            self._buffer3d.SetMaxDistance(max_distance, lib.DS3D_IMMEDIATE)
            self.unlock()

    def set_pitch(self, pitch):
        frequency = int(pitch * self.audio_format.sample_rate)
        self.lock()
        self._buffer.SetFrequency(frequency)
        self.unlock()

    def set_cone_orientation(self, cone_orientation):
        if self._buffer3d:
            x, y, z = cone_orientation
            self.lock()
            self._buffer3d.SetConeOrientation(x, y, -z, lib.DS3D_IMMEDIATE)
            self.unlock()

    def set_cone_inner_angle(self, cone_inner_angle):
        if self._buffer3d:
            self._cone_inner_angle = int(cone_inner_angle)
            self._set_cone_angles()

    def set_cone_outer_angle(self, cone_outer_angle):
        if self._buffer3d:
            self._cone_outer_angle = int(cone_outer_angle)
            self._set_cone_angles()

    def _set_cone_angles(self):
        inner = min(self._cone_inner_angle, self._cone_outer_angle)
        outer = max(self._cone_inner_angle, self._cone_outer_angle)
        self.lock()
        self._buffer3d.SetConeAngles(inner, outer, lib.DS3D_IMMEDIATE)
        self.unlock()

    def set_cone_outer_gain(self, cone_outer_gain):
        if self._buffer3d:
            volume = _db(cone_outer_gain)
            self.lock()
            self._buffer3d.SetConeOutsideVolume(volume, lib.DS3D_IMMEDIATE)
            self.unlock()

class DirectSoundDriver(mt_media.AbstractAudioDriver):
    def __init__(self):
        self._dsound = lib.IDirectSound()
        lib.DirectSoundCreate(None, ctypes.byref(self._dsound), None)

        # A trick used by mplayer.. use desktop as window handle since it
        # would be complex to use pyglet window handles (and what to do when
        # application is audio only?).
        hwnd = _user32.GetDesktopWindow()
        self._dsound.SetCooperativeLevel(hwnd, lib.DSSCL_NORMAL)

        # Create primary buffer with 3D and volume capabilities
        self._buffer = lib.IDirectSoundBuffer()
        dsbd = lib.DSBUFFERDESC()
        dsbd.dwSize = ctypes.sizeof(dsbd)
        dsbd.dwFlags = (lib.DSBCAPS_CTRL3D |
                        lib.DSBCAPS_CTRLVOLUME |
                        lib.DSBCAPS_PRIMARYBUFFER)
        self._dsound.CreateSoundBuffer(dsbd, ctypes.byref(self._buffer), None)

        # Create listener
        self._listener = lib.IDirectSound3DListener()
        self._buffer.QueryInterface(lib.IID_IDirectSound3DListener, 
                                    ctypes.byref(self._listener)) 

        # Create worker thread
        self.worker = DirectSoundWorker()
        self.worker.start()

    def __del__(self):
        try:
            if self._buffer:
                self.delete()
        except:
            pass

    def create_audio_player(self, source_group, player):
        return DirectSoundAudioPlayer(source_group, player)

    def delete(self):
        self.worker.stop()
        self._buffer.Release()
        self._buffer = None
        self._listener.Release()
        self._listener = None
        
    # Listener API
      
    def _set_volume(self, volume):
        self._volume = volume
        self._buffer.SetVolume(_db(volume))

    def _set_position(self, position):
        self._position = position
        x, y, z = position
        self._listener.SetPosition(x, y, -z, lib.DS3D_IMMEDIATE)

    def _set_forward_orientation(self, orientation):
        self._forward_orientation = orientation
        self._set_orientation()

    def _set_up_orientation(self, orientation):
        self._up_orientation = orientation
        self._set_orientation()

    def _set_orientation(self):
        x, y, z = self._forward_orientation
        ux, uy, uz = self._up_orientation
        self._listener.SetOrientation(x, y, -z, ux, uy, -uz, lib.DS3D_IMMEDIATE)

def create_audio_driver():
    global driver
    driver = DirectSoundDriver()
    return driver

# Global driver needed for access to worker thread and _dsound
driver = None
