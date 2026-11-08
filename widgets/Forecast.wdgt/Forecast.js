/*
 * Forecast: a Dashboard weather widget for Mac OS X Lion, with data from Open-Meteo.
 *
 * Dashboard's WebKit stops at TLS 1.0, so every request goes through LionKit's curl
 * (~/Library/LionKit/bin/lk-curl) with widget.system(), which runs the command through /bin/sh.
 */

var CURL = '"$HOME/Library/LionKit/bin/lk-curl"';
var FORECAST_API = "https://api.open-meteo.com/v1/forecast";
var GEOCODING_API = "https://geocoding-api.open-meteo.com/v1/search";
var REFRESH_MINUTES = 30;   // while Dashboard is showing
var STALE_MINUTES = 10;     // refresh on show if the data is older than this

// Window and panel heights; keep in step with Forecast.css.
var WIDTH = 300, COLLAPSED = 110, EXPANDED = 222, BACK = 202;
var PANEL_CLOSED = 58, PANEL_OPEN = 170, FORECAST = 112;

var FAHRENHEIT_COUNTRIES = { US: 1, LR: 1, MM: 1, BS: 1, BZ: 1, KY: 1, PW: 1, FM: 1, MH: 1 };
var DAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

var state = { place: null, units: null, expanded: true, data: null, fetchedAt: 0, error: null, busy: false };
var timer = null;
var search = { timer: null, text: null, busy: false, results: [], doneWhenFound: false };


// --- Preferences --------------------------------------------------------------------------
// Each copy of the widget keeps its own settings. A bare key (no instance prefix) is the
// default for new copies, so a place can be preset from Terminal:
//   defaults write widget-page.zepto.widget.forecast place '{"name":"...","label":"...","lat":0,"lon":0,"cc":"XX"}'

function key(name) {
    return widget.identifier + "-" + name;
}

function pref(name) {
    if (!window.widget) return null;
    var value = widget.preferenceForKey(key(name));
    if (value === undefined || value === null) value = widget.preferenceForKey(name);
    return value === undefined ? null : value;
}

function setPref(name, value) {
    if (window.widget) widget.setPreferenceForKey(value, key(name));
}

function jsonPref(name) {
    try {
        var value = pref(name);
        return value ? JSON.parse(value) : null;
    } catch (e) {
        return null;
    }
}

function placeKey(place) {
    return place ? place.lat + "," + place.lon : "";
}


// --- Fetching -----------------------------------------------------------------------------

function shellQuote(s) {
    return "'" + String(s).replace(/'/g, "'\\''") + "'";
}

function describeFailure(result) {
    var err = result.errorString || "";
    if (result.status === 127 || /No such file|not found/.test(err)) return "missing";
    if (result.status === 6 || result.status === 7 || result.status === 28 || result.status === 35) return "offline";
    return "failed";
}

// done(data, problem): problem is "missing" (no LionKit), "offline" or "failed".
function fetchJSON(url, done) {
    if (!window.widget || !widget.system) {
        done(null, "failed");
        return;
    }
    widget.system(CURL + " -sS --fail --compressed --max-time 20 " + shellQuote(url), function (result) {
        var data = null;
        if (result.status === 0) {
            try {
                data = JSON.parse(result.outputString);
            } catch (e) {
                data = null;
            }
        }
        done(data, data ? null : describeFailure(result));
    });
}

function refresh() {
    var place = state.place;
    if (!place || state.busy) return;
    var url = FORECAST_API + "?latitude=" + place.lat + "&longitude=" + place.lon +
        "&current=temperature_2m,weather_code,is_day" +
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset" +
        "&timezone=auto&forecast_days=7";
    state.busy = true;
    fetchJSON(url, function (data, problem) {
        state.busy = false;
        if (place !== state.place) {        // the place changed while we were waiting
            refresh();
            return;
        }
        if (data && data.current && data.daily) {
            state.data = data;
            state.fetchedAt = new Date().getTime();
            state.error = null;
            setPref("cache", JSON.stringify({ key: placeKey(place), at: state.fetchedAt, data: data }));
        } else {
            state.error = problem;
        }
        render();
    });
}

function startTimer() {
    stopTimer();
    timer = setInterval(refresh, REFRESH_MINUTES * 60000);
}

function stopTimer() {
    if (timer) clearInterval(timer);
    timer = null;
}


// --- Front --------------------------------------------------------------------------------

function units() {
    if (state.units) return state.units;
    return state.place && FAHRENHEIT_COUNTRIES[state.place.cc] ? "F" : "C";
}

function degrees(celsius) {
    if (celsius === null || celsius === undefined) return "";
    var value = Math.round(units() === "F" ? celsius * 9 / 5 + 32 : celsius);
    return (value < 0 ? "−" + (-value) : String(value)) + "°";
}

// The place's own date and time ("2026-11-08", "2026-11-08T17:05"), from its UTC offset.
function localNow(data) {
    return new Date(new Date().getTime() + (data.utc_offset_seconds || 0) * 1000).toISOString().slice(0, 16);
}

function isNight(data) {
    var now = localNow(data), daily = data.daily, i = indexOf(daily.time, now.slice(0, 10));
    if (i >= 0 && daily.sunrise && daily.sunset) return now < daily.sunrise[i] || now >= daily.sunset[i];
    return data.current.is_day === 0;
}

function indexOf(list, value) {
    for (var i = 0; i < (list || []).length; i++) {
        if (list[i] === value) return i;
    }
    return -1;
}

function dayName(isoDate) {
    var p = isoDate.split("-");
    return DAYS[new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])).getUTCDay()];
}

function setText(id, text) {
    document.getElementById(id).innerText = text;
}

var PROBLEMS = { missing: "LionKit missing", offline: "Can’t connect", failed: "No weather data" };

function render() {
    var data = state.data, place = state.place;
    var night = data ? isNight(data) : false;
    document.getElementById("front").className = night ? "night" : "day";

    setText("city", place ? place.name : "Forecast");
    var art = document.getElementById("art");
    if (!data) {
        setText("temp", "--");
        setText("high", "");
        setText("low", !place ? "No city chosen" : state.error ? PROBLEMS[state.error] : "Updating…");
        Art.draw(art, null);
        drawDays(null);
        return;
    }

    var daily = data.daily, today = Math.max(0, indexOf(daily.time, localNow(data).slice(0, 10)));
    var code = data.current.weather_code;
    setText("temp", degrees(data.current.temperature_2m));
    setText("high", "H: " + degrees(daily.temperature_2m_max[today]));
    setText("low", "L: " + degrees(daily.temperature_2m_min[today]));
    Art.draw(art, code, { night: night });
    art.title = Art.names[Art.kindFor(code)];
    drawDays(data, today);
}

function buildDays() {
    var forecast = document.getElementById("forecast");
    for (var i = 0; i < 6; i++) {
        var column = document.createElement("div");
        column.className = "column";
        column.style.left = (8 + i * 44) + "px";
        column.innerHTML = '<div class="dname"></div><canvas class="mini" width="44" height="36"></canvas>' +
                           '<div class="hi"></div><div class="lo"></div>';
        forecast.appendChild(column);
        if (i) {
            var line = document.createElement("div");
            line.className = "grid";
            line.style.left = (8 + i * 44) + "px";
            forecast.appendChild(line);
        }
    }
}

function drawDays(data, start) {
    var columns = document.getElementById("forecast").getElementsByClassName("column");
    for (var i = 0; i < columns.length; i++) {
        var parts = columns[i].childNodes, d = data ? start + i : -1;
        var known = data && d < data.daily.time.length;
        parts[0].innerText = known ? dayName(data.daily.time[d]) : "";
        Art.draw(parts[1], known ? data.daily.weather_code[d] : null, { mini: true });
        parts[2].innerText = known ? degrees(data.daily.temperature_2m_max[d]) : "";
        parts[3].innerText = known ? degrees(data.daily.temperature_2m_min[d]) : "";
    }
}

function resizeWindow(height) {
    if (window.widget) window.resizeTo(WIDTH, height);
}

function applyExpanded(animate) {
    var panel = document.getElementById("panel"), forecast = document.getElementById("forecast");
    panel.className = animate ? "" : "still";
    forecast.className = animate ? "" : "still";
    if (state.expanded) {
        resizeWindow(EXPANDED);
        panel.style.height = PANEL_OPEN + "px";
        forecast.style.height = FORECAST + "px";
    } else {
        panel.style.height = PANEL_CLOSED + "px";
        forecast.style.height = "0px";
        setTimeout(function () {
            if (!state.expanded) resizeWindow(COLLAPSED);
        }, animate ? 320 : 0);
    }
}

function toggleForecast(event) {
    if (!state.place) {
        showBack(event);
        return;
    }
    state.expanded = !state.expanded;
    setPref("expanded", state.expanded ? "1" : "0");
    applyExpanded(true);
}


// --- Back ---------------------------------------------------------------------------------

var linenDrawn = false;

function showBack(event) {
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }
    stopTimer();
    if (window.widget) {
        resizeWindow(Math.max(state.expanded ? EXPANDED : COLLAPSED, BACK));
        widget.prepareForTransition("ToBack");
    }
    if (!linenDrawn) {
        Art.linen(document.getElementById("linen"), 8, 38, 284, 150, 11);
        linenDrawn = true;
    }
    document.getElementById("front").style.display = "none";
    document.getElementById("back").style.display = "block";
    var field = document.getElementById("place");
    field.value = state.place ? state.place.label : "";
    document.getElementById("units").value = units();
    showMatches([], "");
    search.text = null;
    if (window.widget) setTimeout(function () { widget.performTransition(); }, 0);
    setTimeout(function () {
        field.focus();
        field.select();
    }, 0);
}

function showFront() {
    if (window.widget) widget.prepareForTransition("ToFront");
    document.getElementById("back").style.display = "none";
    document.getElementById("front").style.display = "block";
    render();
    if (window.widget) setTimeout(function () { widget.performTransition(); }, 0);
    setTimeout(function () { applyExpanded(false); }, 800);   // after the flip
    refresh();
    startTimer();
}

function trim(s) {
    return s.replace(/^\s+|\s+$/g, "");
}

function placeLabel(r) {
    var bits = [r.name];
    if (r.admin1 && r.admin1 !== r.name) bits.push(r.admin1);
    if (r.country && r.country !== r.name) bits.push(r.country);
    return bits.join(", ");
}

// "Springfield, Illinois" searches for Springfield and keeps the matches that mention Illinois.
function runSearch(text) {
    clearTimeout(search.timer);
    var parts = text.split(","), name = trim(parts[0]);
    var qualifier = trim(parts.slice(1).join(",")).toLowerCase();
    search.text = text;
    search.busy = true;
    showMatches([], "Looking up “" + text + "”…");
    var url = GEOCODING_API + "?count=10&language=en&format=json&name=" + encodeURIComponent(name);
    fetchJSON(url, function (data, problem) {
        if (text !== search.text) return;   // typing moved on
        search.busy = false;
        if (!data) {
            search.doneWhenFound = false;
            showMatches([], problem === "missing" ? "LionKit isn’t installed in ~/Library/LionKit."
                                                  : "Can’t reach Open-Meteo. Check the network and try again.");
            return;
        }
        var seen = {}, found = [], results = data.results || [];
        for (var i = 0; i < results.length; i++) {
            var r = results[i], label = placeLabel(r);
            if (seen[label]) continue;
            seen[label] = true;
            if (qualifier && label.toLowerCase().indexOf(qualifier) < 0 &&
                (r.country_code || "").toLowerCase() !== qualifier) continue;
            found.push({ name: r.name, label: label, lat: r.latitude, lon: r.longitude, cc: r.country_code || "" });
        }
        showMatches(found, found.length ? (found.length > 1 ? "Choose a place:" : "")
                                        : "No place called “" + text + "”. Try a nearby town.");
        if (search.doneWhenFound) {
            search.doneWhenFound = false;
            if (found.length) done();
        }
    });
}

function showMatches(found, message) {
    search.results = found;
    setText("status", message);
    var select = document.getElementById("matches");
    select.innerHTML = "";
    for (var i = 0; i < found.length; i++) {
        var option = document.createElement("option");
        option.value = String(i);
        option.text = found[i].label;
        select.appendChild(option);
    }
    select.style.display = found.length ? "block" : "none";
}

function placeTyped() {
    clearTimeout(search.timer);
    search.doneWhenFound = false;
    var text = trim(document.getElementById("place").value);
    if (text.length < 2 || (state.place && text === state.place.label)) {
        search.text = null;
        showMatches([], "");
        return;
    }
    search.timer = setTimeout(function () { runSearch(text); }, 600);
}

function placeKeyPress(event) {
    if (event.keyCode === 13 || event.keyCode === 3) {
        event.preventDefault();
        done();
    }
}

function unitsChanged() {
    state.units = document.getElementById("units").value;
    setPref("units", state.units);
}

// The Done button (and Return): use the chosen match, looking it up first if needed.
function done() {
    var text = trim(document.getElementById("place").value);
    if (text && !(state.place && text === state.place.label)) {
        if (text !== search.text || search.busy) {
            search.doneWhenFound = true;
            if (text !== search.text) runSearch(text);
            return;
        }
        if (!search.results.length) return;
        var choice = search.results[document.getElementById("matches").selectedIndex] || search.results[0];
        if (placeKey(choice) !== placeKey(state.place)) {
            state.data = null;
            state.error = null;
            state.fetchedAt = 0;
        }
        state.place = choice;
        setPref("place", JSON.stringify(choice));
    }
    if (state.place) showFront();
}

function openCredit(event) {
    event.stopPropagation();
    if (window.widget) widget.openURL("https://open-meteo.com/");
}


// --- Dashboard ----------------------------------------------------------------------------

function onshow() {
    if (state.place && new Date().getTime() - state.fetchedAt > STALE_MINUTES * 60000) refresh();
    startTimer();
}

function onhide() {
    stopTimer();
}

function onremove() {
    var names = ["place", "units", "expanded", "cache"];
    for (var i = 0; i < names.length; i++) setPref(names[i], null);
}

function setup() {
    buildDays();
    new AppleInfoButton(document.getElementById("infobutton"), document.getElementById("front"),
                        "white", "white", showBack);
    new AppleGlassButton(document.getElementById("done"), "Done", done);

    state.place = jsonPref("place");
    state.units = pref("units");
    state.expanded = pref("expanded") !== "0";
    var cache = jsonPref("cache");
    if (cache && state.place && cache.key === placeKey(state.place)) {
        state.data = cache.data;
        state.fetchedAt = cache.at;
    }
    applyExpanded(false);
    render();

    if (window.widget) {
        widget.onshow = onshow;
        widget.onhide = onhide;
        widget.onremove = onremove;
    }
    if (state.place) {
        refresh();
        startTimer();
    } else {
        setTimeout(showBack, 500);   // a new widget: ask where first
    }
}
