# -*- coding: utf-8 -*-
"""Measuring tools, off unless `defaults write page.zepto.kassett DebugPerf -bool yes` is set.

A hitch detector: a background thread watches a heartbeat the main thread updates every 20 ms, and
when the main thread falls more than 100 ms behind, it logs how long the freeze lasted and which
Python code was running (from sys._current_frames). A profiler: cProfile runs on the main thread and
the busiest functions are written out every 30 seconds. Results go to ~/Library/Logs/Kassett-perf.txt
and ~/Library/Logs/Kassett-profile.txt."""
import cProfile
import os
import pstats
import StringIO
import sys
import threading
import time
import traceback

from Foundation import NSObject, NSRunLoop, NSRunLoopCommonModes, NSTimer

HITCHES = os.path.expanduser("~/Library/Logs/Kassett-perf.txt")
PROFILE = os.path.expanduser("~/Library/Logs/Kassett-profile.txt")
STALL = 0.1


def write(path, text, mode="a"):
    with open(path, mode) as f:
        f.write(text.encode("utf-8") if isinstance(text, unicode) else text)
        f.write("\n")


def where(frame):
    """The innermost few Python frames, innermost first."""
    if frame is None:
        return "(no Python frame: in AppKit or the window server)"
    stack = traceback.extract_stack(frame)[-7:]
    return " < ".join("%s:%d %s" % (os.path.basename(f), line, fn) for f, line, fn, _ in reversed(stack))


class Perf(NSObject):
    def start(self):
        self.beat = time.time()
        self.main = threading.current_thread().ident
        self.started = time.time()
        write(HITCHES, "---- Kassett started %s" % time.strftime("%H:%M:%S"), "w")
        self.profiler = cProfile.Profile()
        self.profiler.enable()
        for interval, sel in ((0.02, "beat:"), (30.0, "dump:")):
            t = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(interval, self, sel, None, True)
            NSRunLoop.currentRunLoop().addTimer_forMode_(t, NSRunLoopCommonModes)
        watcher = threading.Thread(target=self.watch)
        watcher.daemon = True
        watcher.start()

    def beat_(self, timer):
        self.beat = time.time()

    def watch(self):
        since, seen = None, None
        while True:
            time.sleep(0.02)
            behind = time.time() - self.beat
            if behind > STALL:
                if since is None:
                    since = self.beat
                    seen = where(sys._current_frames().get(self.main))
            elif since is not None:
                write(HITCHES, "%6.1fs  hitch %4d ms  %s" % (since - self.started, (time.time() - since) * 1000, seen))
                since = None

    def dump_(self, timer):
        self.profiler.disable()
        out = StringIO.StringIO()
        stats = pstats.Stats(self.profiler, stream=out)
        stats.sort_stats("time").print_stats(30)      # Python 2.7.1 calls it "time", not "tottime"
        stats.sort_stats("cumulative").print_stats(30)
        write(PROFILE, "Kassett profile after %d s on the main thread\n%s" % (time.time() - self.started, out.getvalue()), "w")
        self.profiler.enable()

    def mark(self, text):
        write(HITCHES, "%6.1fs  %s" % (time.time() - self.started, text))


perf = None


def start():
    global perf
    perf = Perf.alloc().init()
    perf.start()
    return perf


def mark(text):
    if perf is not None:
        perf.mark(text)
