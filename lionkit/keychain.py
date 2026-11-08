"""Store secrets in the user's login keychain via /usr/bin/security.

The apps run a copy of Apple's Python binary inside their own bundle, whose code signature
the Keychain rejects (-67061) when it builds an item's access list. Going through the
`security` tool avoids that: it owns the items, so reads don't prompt. Secrets are passed
on stdin (security -i), never on the command line.
"""
import re
import subprocess

SECURITY = "/usr/bin/security"
NOT_FOUND = 44


def _quote(s):
    if isinstance(s, unicode):
        s = s.encode("utf-8")
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


def get(service, account):
    p = subprocess.Popen([SECURITY, "find-generic-password", "-s", service, "-a", account, "-g"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, err = p.communicate()
    if p.returncode == NOT_FOUND:
        return None
    if p.returncode != 0:
        raise OSError("Keychain lookup failed: %s" % err.strip())
    m = re.search(r'^password: (?:0x([0-9A-Fa-f]+)\s.*|"(.*)")$', err, re.M)
    if not m:
        return None  # item exists but has no password
    raw = m.group(1).decode("hex") if m.group(1) else m.group(2)
    return raw.decode("utf-8")


def set(service, account, secret):
    command = "add-generic-password -U -s %s -a %s -w %s\n" % (_quote(service), _quote(account), _quote(secret))
    p = subprocess.Popen([SECURITY, "-i"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate(command)
    if "returned" in err or p.returncode not in (0, None):
        raise OSError("Keychain save failed: %s" % (err.strip() or p.returncode))


def delete(service, account):
    subprocess.call([SECURITY, "delete-generic-password", "-s", service, "-a", account],
                    stdout=open("/dev/null", "w"), stderr=subprocess.STDOUT)
