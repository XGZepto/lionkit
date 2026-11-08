"""Ghost Admin API client (https://ghost.org/docs/admin-api/) for Lion."""
import base64
import binascii
import hashlib
import hmac
import json
import mimetypes
import time

from lionkit import http


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip("=")


def admin_token(admin_key):
    """Short-lived JWT from an Admin API key ("<id>:<hex secret>")."""
    key_id, secret = admin_key.strip().split(":")
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT", "kid": key_id}))
    payload = _b64url(json.dumps({"iat": now, "exp": now + 5 * 60, "aud": "/admin/"}))
    signing_input = header + "." + payload
    sig = hmac.new(binascii.unhexlify(secret), signing_input, hashlib.sha256).digest()
    return signing_input + "." + _b64url(sig)


class GhostError(Exception):
    pass


class GhostConflict(GhostError):
    pass


class GhostNotFound(GhostError):
    pass


class Ghost(object):
    def __init__(self, site_url, admin_key):
        self.site = site_url.rstrip("/")
        self.key = admin_key

    def _headers(self):
        return {"Authorization": "Ghost " + admin_token(self.key), "Accept-Version": "v6.0"}

    def _check(self, r, what):
        if not r.ok:
            try:
                msg = r.json()["errors"][0]["message"]
            except Exception:
                msg = (r.body or "")[:200]
            raise GhostError("%s failed (HTTP %d): %s" % (what, r.status, msg))
        return r.json()

    def site_info(self):
        r = http.request("GET", self.site + "/ghost/api/admin/site/", headers=self._headers())
        return self._check(r, "Site lookup")["site"]

    def upload_image(self, path):
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"
        r = http.request("POST", self.site + "/ghost/api/admin/images/upload/", headers=self._headers(),
                         files={"file": (path, mime)}, fields={"purpose": "image"}, timeout=120)
        return self._check(r, "Image upload")["images"][0]["url"]

    def list_posts(self):
        """Every post (newest edit first) with the fields a post list needs."""
        fields = "id,title,status,updated_at,published_at,url,slug"
        r = http.request("GET", self.site + "/ghost/api/admin/posts/?limit=all&order=updated_at%%20desc&fields=%s" % fields,
                         headers=self._headers())
        return self._check(r, "Post list")["posts"]

    def get_post(self, post_id, html=False):
        q = "?formats=html&include=tags" if html else ""
        r = http.request("GET", self.site + "/ghost/api/admin/posts/%s/%s" % (post_id, q), headers=self._headers())
        return self._check(r, "Post lookup")["posts"][0]

    def create_post(self, fields):
        r = http.request("POST", self.site + "/ghost/api/admin/posts/?source=html",
                         headers=self._headers(), json_body={"posts": [fields]})
        return self._check(r, "Post creation")["posts"][0]

    def update_post(self, post_id, fields, updated_at):
        """Update a post. `updated_at` must be the version the edit started from; if the post has
        changed in Ghost since, this raises GhostConflict instead of overwriting."""
        body = dict(fields, updated_at=updated_at)
        source = "?source=html" if "html" in fields else ""
        r = http.request("PUT", self.site + "/ghost/api/admin/posts/%s/%s" % (post_id, source),
                         headers=self._headers(), json_body={"posts": [body]})
        if r.status == 409:
            raise GhostConflict("This post was changed on the site since you opened it.")
        if r.status == 404:
            raise GhostNotFound("This post no longer exists on the site.")
        return self._check(r, "Post update")["posts"][0]

    def delete_post(self, post_id):
        r = http.request("DELETE", self.site + "/ghost/api/admin/posts/%s/" % post_id, headers=self._headers())
        if r.status != 204:
            self._check(r, "Post deletion")

    def tag_names(self):
        r = http.request("GET", self.site + "/ghost/api/admin/tags/?limit=all&fields=name", headers=self._headers())
        return sorted(t["name"] for t in self._check(r, "Tag list")["tags"])

    def editor_url(self, post_id):
        return "%s/ghost/#/editor/post/%s" % (self.site, post_id)
