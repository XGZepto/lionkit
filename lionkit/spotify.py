"""Spotify Web API client with PKCE login (no client secret needed) for Lion.

Login opens the default browser (Momiji) at Spotify's consent page; a tiny server on
127.0.0.1 catches the redirect. The refresh token is kept in the login keychain.
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
    "user-read-private",                                    # profile: name, avatar, Premium
    "user-library-read", "user-library-modify",             # Liked Songs, saved albums
    "playlist-read-private", "playlist-read-collaborative",
    "user-read-recently-played", "user-top-read", "user-follow-read",
])
KEYCHAIN_SERVICE = "LionKit Spotify"


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip("=")


class SpotifyError(Exception):
    pass


class Spotify(object):
    def __init__(self, client_id):
        self.client_id = client_id
        self.access_token = None
        self.expires_at = 0
        self.keychain_error = None
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
            raise SpotifyError(data.get("error_description") or data.get("error") or "HTTP %d" % r.status)
        self.access_token = data["access_token"]
        self.granted = set((data.get("scope") or "").split())
        self.expires_at = time.time() + data.get("expires_in", 3600) - 60
        if data.get("refresh_token"):
            self.refresh_token = data["refresh_token"]
            keychain.set(KEYCHAIN_SERVICE, self.client_id, self.refresh_token)

    def _ensure_token(self):
        if not self.refresh_token:
            raise SpotifyError("Not logged in")
        if not self.access_token or time.time() > self.expires_at:
            self._token_request({"grant_type": "refresh_token", "refresh_token": self.refresh_token})

    # --- Web API -----------------------------------------------------------------------
    def call(self, method, path, json_body=None):
        self._ensure_token()
        r = http.request(method, API + path, json_body=json_body,
                         headers={"Authorization": "Bearer " + self.access_token}, timeout=15)
        if r.status == 204 or not r.body:
            return None
        if not r.ok:
            try:
                msg = r.json()["error"]["message"]
            except Exception:
                msg = "HTTP %d" % r.status
            raise SpotifyError(msg)
        return r.json()

    def now_playing(self):
        return self.call("GET", "/me/player")

    def play(self):
        self.call("PUT", "/me/player/play")

    def pause(self):
        self.call("PUT", "/me/player/pause")

    def next(self):
        self.call("POST", "/me/player/next")

    def previous(self):
        self.call("POST", "/me/player/previous")

    def set_volume(self, percent):
        self.call("PUT", "/me/player/volume?volume_percent=%d" % percent)

    def seek(self, ms):
        self.call("PUT", "/me/player/seek?position_ms=%d" % ms)

    def devices(self):
        """Spotify Connect devices: dicts with id, name, type, is_active, is_restricted, volume_percent."""
        return (self.call("GET", "/me/player/devices") or {}).get("devices", [])

    def transfer(self, device_id, play):
        self.call("PUT", "/me/player", {"device_ids": [device_id], "play": bool(play)})

    def me(self):
        return self.call("GET", "/me")

    def missing_scopes(self):
        """Scopes this build wants that the saved login didn't grant (log in again to add them)."""
        return set(SCOPES.split()) - self.granted if self.granted is not None else set()
