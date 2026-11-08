"""HTTPS for Lion via LionKit's bundled curl (OpenSSL 3)."""
import json
import os
import shutil
import subprocess
import tempfile

LIONKIT = os.path.expanduser("~/Library/LionKit")
CURL = os.path.join(LIONKIT, "bin", "curl")
CA_BUNDLE = os.path.join(LIONKIT, "share", "curl-ca-bundle.crt")
_ENV = dict(os.environ, DYLD_LIBRARY_PATH=os.path.join(LIONKIT, "lib"))


class HTTPError(Exception):
    def __init__(self, message, response=None):
        Exception.__init__(self, message)
        self.response = response


class Response(object):
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    @property
    def ok(self):
        return 200 <= self.status < 300

    def json(self):
        return json.loads(self.body) if self.body else None


def _parse_headers(raw):
    headers = {}
    # With redirects curl writes several header blocks; keep the last one.
    block = raw.replace("\r\n", "\n").strip().split("\n\n")[-1]
    for line in block.split("\n")[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return headers


def request(method, url, headers=None, body=None, json_body=None, files=None, fields=None,
            timeout=30, output_path=None):
    """Make an HTTPS request. Header values (which may hold tokens) are passed to curl
    through a private temp file rather than the command line.

    files:  {"field": (path, mime_type)} for multipart uploads
    fields: {"field": "value"} extra multipart text fields
    output_path: write the body to this file instead of returning it (binary downloads)
    """
    headers = dict(headers or {})
    if json_body is not None:
        body = json.dumps(json_body)
        headers.setdefault("Content-Type", "application/json")
    if isinstance(body, unicode):
        body = body.encode("utf-8")

    tmp = tempfile.mkdtemp(prefix="lionkit-")
    os.chmod(tmp, 0o700)
    try:
        header_file = os.path.join(tmp, "req-headers")
        with open(header_file, "w") as f:
            for k, v in headers.items():
                f.write((u"%s: %s\n" % (k, v)).encode("utf-8"))
        resp_headers = os.path.join(tmp, "resp-headers")
        resp_body = output_path or os.path.join(tmp, "resp-body")

        args = [CURL, "-sS", "-L", "--cacert", CA_BUNDLE, "--max-time", str(timeout),
                "-X", method, "-H", "@" + header_file,
                "-D", resp_headers, "-o", resp_body, "-w", "%{http_code}"]
        if body is not None:
            args += ["--data-binary", "@-"]
        for name, (path, mime) in (files or {}).items():
            args += ["-F", "%s=@%s;type=%s" % (name, path, mime)]
        for name, value in (fields or {}).items():
            args += ["--form-string", "%s=%s" % (name, value)]
        args.append(url)

        p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=_ENV)
        out, err = p.communicate(body)
        if p.returncode != 0:
            raise HTTPError("curl failed (%d): %s" % (p.returncode, err.strip()))
        status = int(out.strip() or 0)
        with open(resp_headers) as f:
            hdrs = _parse_headers(f.read())
        data = None
        if output_path is None:
            with open(resp_body, "rb") as f:
                data = f.read()
        return Response(status, hdrs, data)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def get_json(url, headers=None, timeout=30):
    r = request("GET", url, headers=headers, timeout=timeout)
    if not r.ok:
        raise HTTPError("GET %s -> HTTP %d" % (url, r.status), r)
    return r.json()
