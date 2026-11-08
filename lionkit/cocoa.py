# -*- coding: utf-8 -*-
"""Small PyObjC helpers: background work with main-thread callbacks, and standard menus."""
import threading

from AppKit import (NSAlternateKeyMask, NSApplication, NSCommandKeyMask, NSMenu, NSMenuItem,
                    NSShiftKeyMask)
from Foundation import NSAutoreleasePool, NSObject

_pending = set()


class _MainThreadCall(NSObject):
    def run_(self, _):
        try:
            self.fn()
        finally:
            _pending.discard(self)


def on_main(fn):
    """Run fn() on the main (UI) thread."""
    call = _MainThreadCall.alloc().init()
    call.fn = fn
    _pending.add(call)
    call.performSelectorOnMainThread_withObject_waitUntilDone_("run:", None, False)


def in_background(work, done=None):
    """Run work() on a thread; then done(result, error) on the main thread."""
    def runner():
        pool = NSAutoreleasePool.alloc().init()
        try:
            result, error = work(), None
        except Exception as e:
            result, error = None, e
        if done:
            on_main(lambda: done(result, error))
        del pool
    t = threading.Thread(target=runner)
    t.daemon = True
    t.start()


def _item(menu, title, action, key="", mask=None, target=None):
    item = menu.addItemWithTitle_action_keyEquivalent_(title, action, key)
    if mask is not None:
        item.setKeyEquivalentModifierMask_(mask)
    if target is not None:
        item.setTarget_(target)
    return item


def _add_items(menu, items, delegate):
    for spec in items:
        if spec is None:
            menu.addItem_(NSMenuItem.separatorItem())
        else:
            title, sel, key = spec[:3]
            _item(menu, title, sel, key, spec[3] if len(spec) > 3 else None, target=delegate)


def build_main_menu(app_name, delegate, file_items=(), view_items=(), has_prefs=True):
    """App, File, Edit, View and Window menus. *_items are (title, selector, key[, modifier mask])
    tuples whose actions go to `delegate`; None adds a separator."""
    app = NSApplication.sharedApplication()
    main = NSMenu.alloc().init()

    def submenu(title):
        top = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
        menu = NSMenu.alloc().initWithTitle_(title)
        top.setSubmenu_(menu)
        main.addItem_(top)
        return menu

    m = submenu(app_name)
    _item(m, u"About " + app_name, "orderFrontStandardAboutPanel:")
    from lionkit import updates  # imported here: updates uses this module's in_background
    updates.install(m, 1)
    m.addItem_(NSMenuItem.separatorItem())
    if has_prefs:
        _item(m, u"Preferences…", "showPreferences:", ",", target=delegate)
        m.addItem_(NSMenuItem.separatorItem())
    _item(m, u"Hide " + app_name, "hide:", "h")
    _item(m, u"Hide Others", "hideOtherApplications:", "h", NSCommandKeyMask | NSAlternateKeyMask)
    _item(m, u"Show All", "unhideAllApplications:")
    m.addItem_(NSMenuItem.separatorItem())
    _item(m, u"Quit " + app_name, "terminate:", "q")

    if file_items:
        m = submenu("File")
        _add_items(m, file_items, delegate)
        m.addItem_(NSMenuItem.separatorItem())
        _item(m, u"Close", "performClose:", "w")

    m = submenu("Edit")
    _item(m, u"Undo", "undo:", "z")
    _item(m, u"Redo", "redo:", "z", NSCommandKeyMask | NSShiftKeyMask)
    m.addItem_(NSMenuItem.separatorItem())
    _item(m, u"Cut", "cut:", "x")
    _item(m, u"Copy", "copy:", "c")
    _item(m, u"Paste", "paste:", "v")
    _item(m, u"Select All", "selectAll:", "a")

    if view_items:
        m = submenu("View")
        _add_items(m, view_items, delegate)

    m = submenu("Window")
    _item(m, u"Minimize", "performMiniaturize:", "m")
    _item(m, u"Zoom", "performZoom:")
    app.setWindowsMenu_(m)

    app.setMainMenu_(main)
