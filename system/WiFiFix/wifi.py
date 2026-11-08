# -*- coding: utf-8 -*-
"""Wi-Fi through CoreWLAN, plus the one trick WiFiFix exists for.

Lion reads a WPA2/WPA3 "transition" network's RSN element, finds WPA3's SAE key management next to
WPA2-PSK, and files the network under "WPA2 Enterprise", so it never joins it. Before joining,
WiFiFix rewrites the network's scan record so it offers only WPA2-PSK, which the access point
still accepts from WPA2 clients.

scan() and join() block for seconds: run them through lionkit.cocoa.in_background. status() is
cheap and belongs on the main thread. Demo is a stand-in with made-up networks, for screenshots."""
import time

import objc

objc.loadBundle("CoreWLAN", globals(), "/System/Library/Frameworks/CoreWLAN.framework")

# RSN key management suites (IEEE 802.11, OUI 00-0F-AC)
AKM_PSK, AKM_SAE, AKM_FT_SAE, AKM_OWE = 2, 8, 9, 18
SAE_SUITES = (AKM_SAE, AKM_FT_SAE)
PRIVACY = 0x10  # capability bit: the network is encrypted

# What a network is, as far as Lion and WiFiFix are concerned
OPEN, WEP, WPA, TRANSITION, WPA3, ENTERPRISE = "open", "wep", "wpa", "transition", "wpa3", "enterprise"
JOINABLE = (OPEN, WEP, WPA, TRANSITION)

# join() failures of our own, next to CoreWLAN's negative error codes
NOT_FOUND, NO_WPA2 = 1, 2
STATE_AUTHENTICATING, STATE_ASSOCIATING = 2, 3  # CWInterfaceState

NOTIFICATIONS = ("CWSSIDDidChangeNotification", "CWLinkDidChangeNotification", "CWPowerDidChangeNotification")


def notification_names():
    """CoreWLAN's notification names (the bridge doesn't export them on Lion)."""
    found = {}
    bundle = objc.lookUpClass("NSBundle").bundleWithPath_("/System/Library/Frameworks/CoreWLAN.framework")
    for name in NOTIFICATIONS:
        try:
            objc.loadBundleVariables(bundle, found, [(name, "@")])
        except Exception:
            pass
    return [found[n] for n in NOTIFICATIONS if found.get(n)]


class Status(object):
    def __init__(self, present=True, power=False, ssid=None, rssi=0, busy=False):
        self.present, self.power, self.ssid, self.rssi, self.busy = present, power, ssid, rssi, busy

    def key(self):
        return (self.present, self.power, self.ssid, bars(self.rssi), self.busy)


class Network(object):
    def __init__(self, ssid, rssi, kind):
        self.ssid, self.rssi, self.kind = ssid, rssi, kind

    @property
    def joinable(self):
        return self.kind in JOINABLE

    @property
    def secure(self):
        return self.kind != OPEN


def bars(rssi):
    """Signal strength as 1-4 segments of the Wi-Fi fan."""
    if not rssi:
        return 0
    return 4 if rssi >= -60 else 3 if rssi >= -70 else 2 if rssi >= -80 else 1


def _get(d, key):
    if d is None:
        return None
    return d.objectForKey_(key) if hasattr(d, "objectForKey_") else d.get(key)


def classify(record, privacy=None):
    """The kind of network a scan record describes. `privacy` overrides the capability bit when the
    record doesn't carry one."""
    akms = set(_get(_get(record, "RSN_IE"), "IE_KEY_RSN_AUTHSELS") or [])
    wpa_akms = set(_get(_get(record, "WPA_IE"), "IE_KEY_WPA_AUTHSELS") or [])
    if AKM_PSK in akms:
        return TRANSITION if akms & set(SAE_SUITES) else WPA
    if akms & set(SAE_SUITES):
        return WPA3
    if AKM_PSK in wpa_akms:
        return WPA
    if akms == set([AKM_OWE]):
        return WPA3  # Enhanced Open: as unreachable for Lion as WPA3
    if akms or wpa_akms:
        return ENTERPRISE
    caps = _get(record, "CAPABILITIES")
    if caps is not None:
        return WEP if int(caps) & PRIVACY else OPEN
    return WEP if privacy else OPEN


def strongest(networks):
    """One entry per name: the strongest access point that Lion can join, else the strongest."""
    best = {}
    for n in networks:
        if not n.ssid:
            continue  # hidden network
        old = best.get(n.ssid)
        if old is None or (n.joinable, n.rssi) > (old.joinable, old.rssi):
            best[n.ssid] = n
    return sorted(best.values(), key=lambda n: n.ssid.lower())


def _pair(result):
    """PyObjC returns (value, error) when it knows about an NSError** out-parameter."""
    if isinstance(result, tuple):
        return result[0], result[1]
    return result, None


def offer_wpa2_only(net):
    """Hide the WPA3 (SAE) entry from the network's scan record. False for a WPA3-only access point."""
    rec = net.valueForKey_("scanRecord").mutableCopy()
    rsn = rec.objectForKey_("RSN_IE")
    if rsn is not None:
        akms = list(rsn.objectForKey_("IE_KEY_RSN_AUTHSELS") or [])
        if AKM_PSK not in akms:
            return False
        rsn = rsn.mutableCopy()
        rsn.setObject_forKey_([AKM_PSK], "IE_KEY_RSN_AUTHSELS")
        rec.setObject_forKey_(rsn, "RSN_IE")
        net.setValue_forKey_(rec, "scanRecord")
    return True


class CoreWLAN(object):
    demo = False

    def __init__(self):
        self.iface = CWInterface.interface()  # the main thread's; background work makes its own

    def status(self):
        iface = self.iface or CWInterface.interface()
        if iface is None:
            return Status(present=False)
        self.iface = iface
        power = bool(iface.powerOn())
        ssid = iface.ssid() if power else None
        busy = power and not ssid and iface.interfaceState() in (STATE_AUTHENTICATING, STATE_ASSOCIATING)
        return Status(True, power, ssid or None, iface.rssiValue() if ssid else 0, busy)

    def scan(self, name=None):
        """Networks in range: all of them, or the access points of one network (hidden ones too)."""
        found, _ = _pair(CWInterface.interface().scanForNetworksWithName_error_(name, None))
        nets = []
        for net in found or []:
            rec = net.valueForKey_("scanRecord")
            nets.append(Network(net.ssid(), net.rssiValue(), classify(rec, not net.supportsSecurity_(0))))
        return nets

    def join(self, ssid, password, reconnect=False):
        """Join `ssid`, trying its access points from strongest to weakest. (ok, error code)."""
        iface = CWInterface.interface()
        if reconnect:
            iface.disassociate()
            time.sleep(1.0)
        nets, _ = _pair(iface.scanForNetworksWithName_error_(ssid, None))
        nets = sorted(nets or [], key=lambda n: n.rssiValue(), reverse=True)
        if not nets:
            return False, NOT_FOUND
        code = NO_WPA2
        for net in nets:
            if not offer_wpa2_only(net):
                continue  # WPA3-only access point; Lion can't join it
            ok, err = _pair(iface.associateToNetwork_password_error_(net, password, None))
            if ok:
                return True, None
            code = err.code() if err is not None else -1
        return False, code


DEMO_NETWORKS = (
    (u"Juniper", -47, TRANSITION),
    (u"Bluebird Café", -66, OPEN),
    (u"Harbor Library", -72, WPA),
    (u"Northwind", -61, WPA3),
    (u"Starling 5G", -78, TRANSITION),
    (u"Thornfield Office", -83, ENTERPRISE),
)


class Demo(object):
    """Made-up networks and a Mac that starts in `state` (connected, off, away, failed, joining or
    fresh). Joins take `join_seconds`; the password "wrong" fails, and so does every join in the
    failed state."""
    demo = True

    def __init__(self, state, join_seconds):
        self.state, self.join_seconds = state, join_seconds
        self.power = state != "off"
        self.ssid = u"Juniper" if state in ("connected", "fresh") else None

    def status(self):
        rssi = dict((n, r) for n, r, _ in DEMO_NETWORKS).get(self.ssid, 0)
        return Status(True, self.power, self.ssid, rssi, False)

    def scan(self, name=None):
        time.sleep(1.2)
        nets = [Network(*n) for n in DEMO_NETWORKS if not (self.state == "away" and n[0] == u"Juniper")]
        return [n for n in nets if name is None or n.ssid == name]

    def join(self, ssid, password, reconnect=False):
        if reconnect:
            self.ssid = None
        time.sleep(self.join_seconds)
        if not self.scan(ssid):
            return False, NOT_FOUND
        if self.state == "failed" or password == u"wrong":
            return False, -3924
        self.ssid = ssid
        return True, None
