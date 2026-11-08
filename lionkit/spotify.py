"""Spotify Web API client with PKCE login (no client secret needed) for Lion.

Login opens the default browser (Momiji) at Spotify's consent page; a tiny server on
127.0.0.1 catches the redirect. The refresh token is kept in the login keychain.

Only endpoints that a Development Mode app created after November 2024 may still call are used
here. Spotify took away recommendations, related artists, audio features and editorial playlists
in November 2024, and in February 2026 it removed artist top tracks, the "several items" lookups,
other users' profiles and playlists, and the `product` field on /me. It also moved playlist
contents to /playlists/{id}/items (only for playlists the user owns or collaborates on), merged
saving and following into /me/library, and capped search at 10 results per type.
"""
import base64
import BaseHTTPServer
import hashlib
import json
import os
import threading
import time
import urllib
import urlparse

from lionkit import http, keychain

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
REDIRECT_PORT = 8888
REDIRECT_URI = "http://127.0.0.1:%d/callback" % REDIRECT_PORT
SCOPES = " ".join([
    "user-read-playback-state", "user-modify-playback-state", "user-read-currently-playing",
    "user-read-private",                                    # profile: name and avatar
    "user-library-read", "user-library-modify",             # Liked Songs, saved albums
    "playlist-read-private", "playlist-read-collaborative",
    "user-read-recently-played", "user-top-read", "user-follow-read",
    "user-follow-modify",                                   # follow and unfollow artists
])
KEYCHAIN_SERVICE = "LionKit Spotify"
PAGE = 50            # most library endpoints return at most 50 items per request
SEARCH_LIMIT = 10    # the most /search (and an artist's albums) return per request since February 2026

# Spotify's machine-readable player errors, in words a person can act on.
REASONS = {
    "PREMIUM_REQUIRED": "Controlling playback needs a Spotify Premium account.",
    "NO_ACTIVE_DEVICE": "Spotify isn't playing anywhere right now. Choose a device from the AirPlay menu.",
    "UNKNOWN": "Spotify couldn't do that on this device.",
}


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip("=")


def _query(params):
    pairs = []
    for k, v in sorted(params.items()):
        if v is None:
            continue
        if isinstance(v, unicode):
            v = v.encode("utf-8")
        pairs.append((k, v))
    return urllib.urlencode(pairs)


def items_of(paging):
    """A playlist item, saved track or saved album wraps its object; return the objects."""
    out = []
    for entry in (paging or {}).get("items") or []:
        if not entry:
            continue
        obj = entry if entry.get("id") else entry.get("item") or entry.get("track") or entry.get("album")
        if obj and obj.get("id"):
            out.append(obj)
    return out


def playlist_items_paging(playlist):
    """Playlists carry their contents under `items` since February 2026 (`tracks` before)."""
    return playlist.get("items") if isinstance(playlist.get("items"), dict) else playlist.get("tracks")


class SpotifyError(Exception):
    def __init__(self, message, status=0, reason=None):
        Exception.__init__(self, message)
        self.status, self.reason = status, reason


class Spotify(object):
    def __init__(self, client_id):
        self.client_id = client_id
        self.access_token = None
        self.expires_at = 0
        self.keychain_error = None
        self.lock = threading.Lock()
        try:
            self.refresh_token = keychain.get(KEYCHAIN_SERVICE, client_id)
        except OSError as e:  # e.g. keychain locked for apps started over SSH
            self.refresh_token, self.keychain_error = None, str(e)
        self.granted = None  # scopes Spotify actually granted, known after the first token request

    @property
    def logged_in(self):
        return bool(self.refresh_token)

    # --- login -------------------------------------------------------------------------
    def begin_login(self, open_url, on_done):
        """Start PKCE login: open_url(url) shows the consent page; on_done(error_or_None) runs
        on a background thread when the browser redirects back."""
        verifier = _b64url(os.urandom(48))
        state = _b64url(os.urandom(12))
        challenge = _b64url(hashlib.sha256(verifier).digest())
        spotify = self

        class Handler(BaseHTTPServer.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                q = urlparse.parse_qs(urlparse.urlparse(self.path).query)
                ok = q.get("state", [None])[0] == state and "code" in q
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                msg = "Logged in. You can close this tab and go back to the app." if ok \
                    else "Login failed: %s" % q.get("error", ["unknown error"])[0]
                self.wfile.write("<html><body style='font:16px Lucida Grande;margin:40px'>%s</body></html>" % msg)
                self.server.result = q.get("code", [None])[0] if ok else None
                self.server.error = None if ok else msg

        def serve():
            server = BaseHTTPServer.HTTPServer(("127.0.0.1", REDIRECT_PORT), Handler)
            server.timeout = 300
            server.result, server.error = None, "Login timed out"
            server.handle_request()
            server.server_close()
            if server.result:
                try:
                    spotify._token_request({"grant_type": "authorization_code", "code": server.result,
                                            "redirect_uri": REDIRECT_URI, "code_verifier": verifier})
                    on_done(None)
                except Exception as e:
                    on_done(str(e))
            else:
                on_done(server.error)

        threading.Thread(target=serve).start()
        open_url(AUTH_URL + "?" + urllib.urlencode({
            "client_id": self.client_id, "response_type": "code", "redirect_uri": REDIRECT_URI,
            "code_challenge_method": "S256", "code_challenge": challenge, "scope": SCOPES, "state": state}))

    def logout(self):
        keychain.delete(KEYCHAIN_SERVICE, self.client_id)
        self.refresh_token = self.access_token = None

    def _token_request(self, params):
        params["client_id"] = self.client_id
        r = http.request("POST", TOKEN_URL, body=urllib.urlencode(params),
                         headers={"Content-Type": "application/x-www-form-urlencoded"})
        data = r.json() if r.body else {}
        if not r.ok:
            raise SpotifyError(data.get("error_description") or data.get("error") or "HTTP %d" % r.status,
                               r.status, data.get("error"))
        self.access_token = data["access_token"]
        self.granted = set((data.get("scope") or "").split())
        self.expires_at = time.time() + data.get("expires_in", 3600) - 60
        if data.get("refresh_token"):
            self.refresh_token = data["refresh_token"]
            keychain.set(KEYCHAIN_SERVICE, self.client_id, self.refresh_token)

    def _stored_token(self):
        try:
            return keychain.get(KEYCHAIN_SERVICE, self.client_id)
        except OSError:
            return None

    def _ensure_token(self):
        with self.lock:  # several background threads may need a fresh token at once
            if self.access_token and time.time() < self.expires_at:
                return
            # Another LionKit process (the Now Playing widget) may have rotated the refresh token.
            self.refresh_token = self._stored_token() or self.refresh_token
            if not self.refresh_token:
                raise SpotifyError("Not logged in")
            used = self.refresh_token
            try:
                self._token_request({"grant_type": "refresh_token", "refresh_token": used})
            except SpotifyError as e:
                stored = self._stored_token()
                if e.reason != "invalid_grant" or not stored or stored == used:
                    raise
                self.refresh_token = stored  # rotated while we were asking: try the new one once
                self._token_request({"grant_type": "refresh_token", "refresh_token": stored})

    # --- Web API -----------------------------------------------------------------------
    def call(self, method, path, json_body=None, params=None, retried=False):
        self._ensure_token()
        url = API + path
        if params:
            url += ("&" if "?" in url else "?") + _query(params)
        r = http.request(method, url, json_body=json_body,
                         headers={"Authorization": "Bearer " + self.access_token}, timeout=15)
        if r.status == 401 and not retried:
            self.access_token = None  # revoked or expired early: refresh once and try again
            return self.call(method, path, json_body, params, True)
        if r.status in (202, 204) or not r.body:
            if not r.ok:
                raise SpotifyError("Spotify answered HTTP %d" % r.status, r.status)
            return None
        if not r.ok:
            reason, msg = None, None
            try:
                err = r.json()["error"]
                msg, reason = err.get("message"), err.get("reason")
            except Exception:
                pass
            if r.status == 403 and msg and "restricted device" in msg.lower():
                # Some Connect devices (many AV receivers, TVs and speaker groups) only obey Spotify's own apps.
                reason, msg = "RESTRICTED", "Only the Spotify app can control this device."
            elif r.status == 403 and msg and "regist" in msg.lower():
                # A Development Mode app only works for accounts its owner added in the dashboard.
                reason, msg = "NOT_ALLOWLISTED", "Spotify hasn't added this account to the app's list of users."
            elif r.status == 429:
                msg = "Spotify asked Kassett to slow down. It will try again in a moment."
            elif reason in REASONS:
                msg = REASONS[reason]
            elif msg and "scope" in msg.lower():
                reason, msg = "SCOPE", "This login doesn't allow that yet. Log in again to give permission."
            raise SpotifyError(msg or "Spotify answered HTTP %d" % r.status, r.status, reason)
        try:
            return r.json()
        except ValueError:
            return None

    # --- player --------------------------------------------------------------------------
    def now_playing(self):
        return self.call("GET", "/me/player", params={"additional_types": "track,episode"})

    def queue(self):
        """{"currently_playing": track, "queue": [tracks...]}"""
        return self.call("GET", "/me/player/queue") or {}

    def add_to_queue(self, uri):
        self.call("POST", "/me/player/queue", params={"uri": uri})

    def play(self):
        self.call("PUT", "/me/player/play")

    def play_context(self, context_uri, offset_uri=None, position=None):
        body = {"context_uri": context_uri}
        if offset_uri:
            body["offset"] = {"uri": offset_uri}
        elif position is not None:
            body["offset"] = {"position": position}
        self.call("PUT", "/me/player/play", body)

    def play_tracks(self, uris, position=0):
        self.call("PUT", "/me/player/play", {"uris": list(uris), "offset": {"position": position}})

    def pause(self):
        self.call("PUT", "/me/player/pause")

    def next(self):
        self.call("POST", "/me/player/next")

    def previous(self):
        self.call("POST", "/me/player/previous")

    def set_volume(self, percent):
        self.call("PUT", "/me/player/volume", params={"volume_percent": int(percent)})

    def seek(self, ms):
        self.call("PUT", "/me/player/seek", params={"position_ms": int(max(0, ms))})

    def set_shuffle(self, on):
        self.call("PUT", "/me/player/shuffle", params={"state": "true" if on else "false"})

    def devices(self):
        """Spotify Connect devices: dicts with id, name, type, is_active, is_restricted, volume_percent."""
        return (self.call("GET", "/me/player/devices") or {}).get("devices", [])

    def transfer(self, device_id, play):
        self.call("PUT", "/me/player", {"device_ids": [device_id], "play": bool(play)})

    # --- the user's library ------------------------------------------------------------------
    def me(self):
        return self.call("GET", "/me")

    def saved_tracks(self, offset=0):
        return self.call("GET", "/me/tracks", params={"limit": PAGE, "offset": offset, "market": "from_token"})

    def saved_albums(self, offset=0):
        return self.call("GET", "/me/albums", params={"limit": PAGE, "offset": offset, "market": "from_token"})

    def followed_artists(self, after=None):
        return (self.call("GET", "/me/following", params={"type": "artist", "limit": PAGE, "after": after})
                or {}).get("artists") or {}

    def my_playlists(self, offset=0):
        return self.call("GET", "/me/playlists", params={"limit": PAGE, "offset": offset})

    def library_contains(self, uris):
        """[True/False per URI] for tracks, albums, artists or playlists in the user's library."""
        return self.call("GET", "/me/library/contains", params={"uris": ",".join(uris[:40])}) or []

    def save(self, uris):
        self.call("PUT", "/me/library", params={"uris": ",".join(uris[:40])})

    def unsave(self, uris):
        self.call("DELETE", "/me/library", params={"uris": ",".join(uris[:40])})

    # --- catalog -----------------------------------------------------------------------------
    def playlist(self, playlist_id):
        """Name, owner, images and, for the user's own playlists, the first page of items."""
        return self.call("GET", "/playlists/%s" % playlist_id, params={"market": "from_token",
                                                                         "additional_types": "track"})

    def playlist_items(self, playlist_id, offset=0):
        return self.call("GET", "/playlists/%s/items" % playlist_id,
                         params={"limit": PAGE, "offset": offset, "market": "from_token",
                                 "additional_types": "track"})

    def album(self, album_id):
        return self.call("GET", "/albums/%s" % album_id, params={"market": "from_token"})

    def album_tracks(self, album_id, offset=0):
        return self.call("GET", "/albums/%s/tracks" % album_id,
                         params={"limit": PAGE, "offset": offset, "market": "from_token"})

    def artist(self, artist_id):
        return self.call("GET", "/artists/%s" % artist_id)

    def artist_albums(self, artist_id, offset=0):
        return self.call("GET", "/artists/%s/albums" % artist_id,
                         params={"include_groups": "album,single", "limit": SEARCH_LIMIT, "offset": offset,
                                 "market": "from_token"})

    def artist_songs(self, artist):
        """Stands in for the removed top-tracks endpoint: Spotify's search ranks an artist's
        own songs by how much they are played, so its first hits are the popular ones."""
        found = self.search(u'artist:"%s"' % artist["name"].replace(u'"', u""), "track")
        tracks = ((found.get("tracks") or {}).get("items") or [])
        return [t for t in tracks if t and any(a.get("id") == artist["id"] for a in t.get("artists") or [])]

    def search(self, text, types="track,artist,album"):
        return self.call("GET", "/search", params={"q": text, "type": types, "limit": SEARCH_LIMIT,
                                                   "market": "from_token"}) or {}

    def missing_scopes(self):
        """Scopes this build wants that the saved login didn't grant (log in again to add them)."""
        return set(SCOPES.split()) - self.granted if self.granted is not None else set()
