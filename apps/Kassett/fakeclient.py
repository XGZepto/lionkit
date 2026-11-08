# -*- coding: utf-8 -*-
"""Sample library data from design/kassett, shaped like Spotify's answers. Only used with the
hidden DebugFakeState setting, so every library screen can be checked without anyone's account."""

ME = {"id": "kassett-demo", "display_name": u"Demo"}
ALBUMS = [(u"The Lion’s Roar", u"First Aid Kit", "2012"), (u"Bon Iver, Bon Iver", u"Bon Iver", "2011"),
          (u"Helplessness Blues", u"Fleet Foxes", "2011"), (u"21", u"Adele", "2011"),
          (u"Born to Die", u"Lana Del Rey", "2012"), (u"Hurry Up, We’re Dreaming", u"M83", "2011"),
          (u"Channel Orange", u"Frank Ocean", "2012"), (u"Sigh No More", u"Mumford & Sons", "2009"),
          (u"The Suburbs", u"Arcade Fire", "2010"), (u"Ceremonials", u"Florence + the Machine", "2011")]
MIX = [(u"Holocene", u"Bon Iver", 336), (u"The Lion’s Roar", u"First Aid Kit", 245),
       (u"Helplessness Blues", u"Fleet Foxes", 304), (u"Someone Like You", u"Adele", 285),
       (u"Video Games", u"Lana Del Rey", 282), (u"Midnight City", u"M83", 243),
       (u"Thinkin Bout You", u"Frank Ocean", 200), (u"The Cave", u"Mumford & Sons", 218),
       (u"Ready to Start", u"Arcade Fire", 255), (u"Shake It Out", u"Florence + the Machine", 277)]
ROAR = [(u"The Lion’s Roar", 245), (u"Emmylou", 256), (u"In the Hearts of Men", 248), (u"Blue", 228),
        (u"This Old Routine", 292), (u"To a Poet", 362), (u"I Found a Way", 221), (u"Dance to Another Tune", 210),
        (u"New Year’s Eve", 239), (u"King of the World", 223)]
PLAYLISTS = [(u"Sunday Morning", True, u"Slow songs for slow mornings."), (u"Road Trip 2011", True, u""),
             (u"Focus", True, u""), (u"Mom’s Favorites", False, u""), (u"Rainy Days", True, u""),
             (u"Kitchen Dancing", True, u"")]
FAKA = [(u"Palomino", "2022"), (u"Ruins", "2018"), (u"Stay Gold", "2014"), (u"The Lion’s Roar", "2012"),
        (u"The Big Black & the Blue", "2010")]
POPULAR = [(u"The Lion’s Roar", u"The Lion’s Roar", 245), (u"My Silver Lining", u"Stay Gold", 219),
           (u"Emmylou", u"The Lion’s Roar", 256), (u"Fireworks", u"Ruins", 241), (u"Angel", u"Palomino", 222),
           (u"Stay Gold", u"Stay Gold", 213), (u"Wolf", u"Stay Gold", 221)]


def slug(text):
    return "".join(c for c in text.lower() if c.isalnum())[:22] or "x"


def artist(name):
    return {"id": "ar" + slug(name), "uri": "spotify:artist:ar" + slug(name), "name": name, "images": []}


def album(name, by, year):
    return {"id": "al" + slug(name), "uri": "spotify:album:al" + slug(name), "name": name, "images": [],
            "artists": [artist(by)], "release_date": year + "-01-01", "total_tracks": 10}


def track(name, by, seconds, album_name=None, year="2011"):
    return {"id": "tr" + slug(name + by), "uri": "spotify:track:tr" + slug(name + by), "name": name,
            "duration_ms": seconds * 1000, "artists": [artist(by)], "album": album(album_name or name, by, year)}


class FakeSpotify(object):
    logged_in = True
    keychain_error = None

    def missing_scopes(self):
        return set()

    def me(self):
        return ME

    def saved_tracks(self, offset=0):
        items = [{"track": track(n, by, s, dict((b, a) for a, b, _ in ALBUMS).get(by))} for n, by, s in reversed(MIX)]
        return {"items": items if not offset else [], "total": 248 if not offset else 248, "next": None}

    def my_playlists(self, offset=0):
        items = [{"id": "pl" + slug(n), "uri": "spotify:playlist:pl" + slug(n), "name": n, "description": d,
                  "owner": ME if mine else {"id": "mom", "display_name": u"Mom"}, "images": [],
                  "items": {"total": 10 if mine else 23}} for n, mine, d in PLAYLISTS]
        return {"items": items, "next": None}

    def playlist(self, playlist_id):
        for n, mine, d in PLAYLISTS:
            if "pl" + slug(n) == playlist_id:
                p = self.my_playlists()["items"][[x[0] for x in PLAYLISTS].index(n)]
                p = dict(p)
                if mine:
                    p["items"] = {"items": [{"item": track(t, by, s, dict((b, a) for a, b, _ in ALBUMS).get(by))}
                                            for t, by, s in MIX], "total": 10}
                else:
                    del p["items"]
                return p
        return {}

    def playlist_items(self, playlist_id, offset=0):
        return {"items": [], "total": 10}

    def saved_albums(self, offset=0):
        return {"items": [{"album": album(*a)} for a in ALBUMS], "total": 10, "next": None}

    def album(self, album_id):
        a = dict(album(*ALBUMS[0]))
        for x in ALBUMS + [(n, u"First Aid Kit", y) for n, y in FAKA]:
            if "al" + slug(x[0]) == album_id:
                a = dict(album(*x))
        a["tracks"] = {"items": [dict(track(n, a["artists"][0]["name"], s), album=None, track_number=i + 1, disc_number=1)
                                 for i, (n, s) in enumerate(ROAR)], "total": 10}
        return a

    def album_tracks(self, album_id, offset=0):
        return {"items": [], "total": 10}

    def library_contains(self, uris):
        return [False for _ in uris]

    def save(self, uris):
        pass

    def unsave(self, uris):
        pass

    def followed_artists(self, after=None):
        return {"items": [artist(by) for _, by, _ in ALBUMS], "total": 10, "cursors": {}, "next": None}

    def artist(self, artist_id):
        for _, by, _ in ALBUMS:
            if "ar" + slug(by) == artist_id:
                return artist(by)
        return artist(u"First Aid Kit")

    def artist_songs(self, a):
        return [track(n, a["name"], s, al) for n, al, s in POPULAR]

    def artist_albums(self, artist_id, offset=0):
        return {"items": [album(n, u"First Aid Kit", y) for n, y in FAKA]}

    def search(self, text, types=None):
        return {"tracks": {"items": [track(u"The Lion Sleeps Tonight", u"The Tokens", 161),
                                     track(u"The Lion’s Roar", u"First Aid Kit", 245),
                                     track(u"Lionhearted", u"Porter Robinson", 268),
                                     track(u"Circle of Life", u"Carmen Twillie", 238)]},
                "artists": {"items": [artist(u"Lionel Richie"), artist(u"LION BABE"), artist(u"First Aid Kit"),
                                      artist(u"The Tokens")]},
                "albums": {"items": [album(u"The Lion King (Soundtrack)", u"Various Artists", "1994"),
                                     album(u"The Lion’s Roar", u"First Aid Kit", "2012"),
                                     album(u"Lionheart", u"Kate Bush", "1978"),
                                     album(u"The Lion and the Cobra", u"Sinéad O’Connor", "1987")]}}
