/*
 * Forecast: weather art drawn with canvas, in the spirit of Lion's glowing weather icons.
 * Everything is drawn in a 100 x 80 box and scaled to the canvas, so the big icon on the
 * front and the six small ones share one set of drawings.
 */

var Art = (function () {
    var TAU = Math.PI * 2;

    // Open-Meteo's WMO weather codes, grouped the way the art draws them.
    function kindFor(code) {
        if (code === 0) return "clear";
        if (code === 1) return "mostlyclear";
        if (code === 2) return "partlycloudy";
        if (code === 3) return "overcast";
        if (code === 45 || code === 48) return "fog";
        if (code >= 51 && code <= 55) return "drizzle";
        if (code === 56 || code === 57 || code === 66 || code === 67) return "sleet";
        if (code >= 61 && code <= 65) return code === 61 ? "lightrain" : "rain";
        if (code >= 71 && code <= 77) return "snow";
        if (code >= 80 && code <= 82) return "showers";
        if (code === 85 || code === 86) return "snowshowers";
        if (code === 95) return "thunder";
        if (code === 96 || code === 99) return "hail";
        return "overcast";
    }

    var NAMES = {
        clear: "Clear", mostlyclear: "Mostly Clear", partlycloudy: "Partly Cloudy",
        overcast: "Cloudy", fog: "Fog", drizzle: "Drizzle", sleet: "Freezing Rain",
        lightrain: "Light Rain", rain: "Rain", snow: "Snow", showers: "Showers",
        snowshowers: "Snow Showers", thunder: "Thunderstorms", hail: "Thunderstorms and Hail"
    };

    // Fraction of the lunar cycle at a date: 0 new, 0.25 first quarter, 0.5 full.
    function moonPhase(date) {
        var synodic = 29.530588853, knownNew = Date.UTC(2000, 0, 6, 18, 14);
        var days = (date.getTime() - knownNew) / 86400000;
        var p = (days % synodic) / synodic;
        return p < 0 ? p + 1 : p;
    }

    // Shadows ignore the canvas transform, so every blur and offset is scaled by hand.
    function shadow(g, s, color, blur, dy) {
        g.shadowColor = color;
        g.shadowBlur = blur * s;
        g.shadowOffsetX = 0;
        g.shadowOffsetY = (dy || 0) * s;
    }

    function noShadow(g) {
        g.shadowColor = "rgba(0,0,0,0)";
        g.shadowBlur = 0;
        g.shadowOffsetY = 0;
    }

    // The glow and rays stop short of the edge of the 100 x 80 box, so they fade out instead
    // of being cut off by the canvas.
    function room(x, y, mini) {
        var r = Math.min(y, 80 - y);
        return mini ? Math.min(r, x, 100 - x) : r;
    }

    function sun(g, s, x, y, r, mini) {
        var reach = Math.min(r * 2.4, room(x, y, mini) - 1);
        var glow = g.createRadialGradient(x, y, r * 0.7, x, y, reach);
        glow.addColorStop(0, "rgba(255, 214, 120, 0.70)");
        glow.addColorStop(0.35, "rgba(255, 190, 80, 0.28)");
        glow.addColorStop(1, "rgba(255, 170, 60, 0)");
        g.fillStyle = glow;
        g.beginPath();
        g.arc(x, y, reach, 0, TAU, false);
        g.fill();

        if (!mini) {
            g.save();
            g.translate(x, y);
            for (var i = 0; i < 18; i++) {
                g.rotate(TAU / 18);
                var len = Math.min(r * (i % 2 ? 1.6 : 2.05), reach - 2);
                var ray = g.createLinearGradient(r, 0, len, 0);
                ray.addColorStop(0, "rgba(255, 240, 180, 0.65)");
                ray.addColorStop(1, "rgba(255, 220, 130, 0)");
                g.fillStyle = ray;
                g.beginPath();
                g.moveTo(r * 0.92, -r * 0.08);
                g.lineTo(len, 0);
                g.lineTo(r * 0.92, r * 0.08);
                g.closePath();
                g.fill();
            }
            g.restore();
        }

        var body = g.createLinearGradient(x, y - r, x, y + r);
        body.addColorStop(0, "#ffb04a");
        body.addColorStop(0.5, "#ffcf3d");
        body.addColorStop(1, "#fff176");
        g.fillStyle = body;
        g.beginPath();
        g.arc(x, y, r, 0, TAU, false);
        g.fill();

        var shine = g.createRadialGradient(x - r * 0.3, y - r * 0.4, 0, x - r * 0.3, y - r * 0.4, r * 0.9);
        shine.addColorStop(0, "rgba(255, 255, 240, 0.85)");
        shine.addColorStop(1, "rgba(255, 255, 240, 0)");
        g.fillStyle = shine;
        g.beginPath();
        g.arc(x, y, r, 0, TAU, false);
        g.fill();

        g.lineWidth = Math.max(0.8 / s, r * 0.07);
        g.strokeStyle = "rgba(255, 252, 225, 0.9)";
        g.beginPath();
        g.arc(x, y, r - g.lineWidth / 2, 0, TAU, false);
        g.stroke();
    }

    function moon(g, s, x, y, r, phase, mini) {
        var reach = Math.min(r * 2.1, room(x, y, mini) - 1);
        var glow = g.createRadialGradient(x, y, r * 0.8, x, y, reach);
        glow.addColorStop(0, "rgba(230, 235, 255, 0.45)");
        glow.addColorStop(1, "rgba(225, 230, 255, 0)");
        g.fillStyle = glow;
        g.beginPath();
        g.arc(x, y, reach, 0, TAU, false);
        g.fill();

        g.fillStyle = "rgba(235, 235, 255, 0.10)";   // earthshine on the dark side
        g.beginPath();
        g.arc(x, y, r, 0, TAU, false);
        g.fill();

        var lit = g.createRadialGradient(x - r * 0.3, y - r * 0.3, 0, x, y, r);
        lit.addColorStop(0, "#ffffff");
        lit.addColorStop(0.6, "#f6f1dc");
        lit.addColorStop(1, "#dcd2b0");
        // Around new moon the real moon all but disappears; keep a slim crescent so the art
        // still reads as night.
        phase = Math.min(Math.max(phase, 0.12), 0.88);
        var k = Math.cos(phase * TAU);          // 1 at new moon, -1 at full
        var crescent = k > 0;
        // The path is built in a flipped, squashed space; the path survives restore(), so the
        // fill (and its gradient) happens back in plain canvas space.
        g.save();
        g.translate(x, y);
        if (phase > 0.5) g.scale(-1, 1);        // waning: lit on the left
        g.beginPath();
        g.arc(0, 0, r, -Math.PI / 2, Math.PI / 2, false);
        g.scale(Math.max(Math.abs(k), 0.001), 1);
        if (crescent) g.arc(0, 0, r, Math.PI / 2, -Math.PI / 2, true);
        else g.arc(0, 0, r, Math.PI / 2, Math.PI * 1.5, false);
        g.closePath();
        g.restore();
        g.fillStyle = lit;
        g.fill();

        g.fillStyle = "rgba(170, 160, 130, 0.22)";
        var craters = [[-0.35, -0.2, 0.18], [0.2, 0.3, 0.14], [0.3, -0.35, 0.1]];
        for (var i = 0; i < craters.length; i++) {
            g.beginPath();
            g.arc(x + craters[i][0] * r, y + craters[i][1] * r, craters[i][2] * r, 0, TAU, false);
            g.fill();
        }
    }

    var CLOUD_TONES = {
        light: ["#ffffff", "#eef2f7", "#bfc9d6"],
        mid: ["#f4f6f9", "#d3dae3", "#9aa6b6"],
        dark: ["#dfe3e9", "#a9b2bf", "#6c7889"]
    };

    // A cumulus centred on (cx, cy), w wide and about 0.56 w tall.
    function cloud(g, s, cx, cy, w, tone, mini) {
        var k = w / 100, x0 = cx - w / 2, y0 = cy - 28 * k;
        function puff(px, py, pr) {
            g.moveTo(x0 + (px + pr) * k, y0 + py * k);
            g.arc(x0 + px * k, y0 + py * k, pr * k, 0, TAU, false);
        }
        function shape() {
            g.beginPath();
            puff(30, 33, 17);
            puff(54, 23, 22);
            puff(76, 35, 15);
            puff(17, 43, 11);
            puff(86, 44, 11);
            g.moveTo(x0 + 17 * k, y0 + 36 * k);   // clockwise, like the arcs, so nothing cancels
            g.lineTo(x0 + 86 * k, y0 + 36 * k);
            g.lineTo(x0 + 86 * k, y0 + 54 * k);
            g.lineTo(x0 + 17 * k, y0 + 54 * k);
            g.closePath();
        }
        var c = CLOUD_TONES[tone || "light"];
        var fill = g.createLinearGradient(0, y0, 0, y0 + 56 * k);
        fill.addColorStop(0, c[0]);
        fill.addColorStop(0.55, c[1]);
        fill.addColorStop(1, c[2]);

        g.save();
        shadow(g, s, "rgba(20, 30, 50, 0.45)", mini ? 2 : 6, mini ? 1 : 2.5);
        g.fillStyle = fill;
        shape();
        g.fill();
        noShadow(g);

        // Light from above: a soft highlight inside the top of the puffs.
        shape();
        g.clip();
        var hi = g.createRadialGradient(x0 + 48 * k, y0 + 4 * k, 0, x0 + 48 * k, y0 + 4 * k, 40 * k);
        hi.addColorStop(0, "rgba(255, 255, 255, 0.75)");
        hi.addColorStop(1, "rgba(255, 255, 255, 0)");
        g.fillStyle = hi;
        g.fillRect(x0, y0, w, 56 * k);
        g.restore();
    }

    function drops(g, s, spots, len, alpha) {
        g.save();
        g.lineCap = "round";
        g.lineWidth = 2.6;
        for (var i = 0; i < spots.length; i++) {
            var x = spots[i][0], y = spots[i][1];
            var grad = g.createLinearGradient(x, y, x - len * 0.3, y + len);
            grad.addColorStop(0, "rgba(160, 200, 255, 0)");
            grad.addColorStop(1, "rgba(200, 228, 255, " + (alpha || 0.95) + ")");
            g.strokeStyle = grad;
            g.beginPath();
            g.moveTo(x, y);
            g.lineTo(x - len * 0.3, y + len);
            g.stroke();
        }
        g.restore();
    }

    function flakes(g, s, spots, r, mini) {
        g.save();
        g.strokeStyle = "rgba(255, 255, 255, 0.95)";
        g.fillStyle = "#ffffff";
        g.lineCap = "round";
        g.lineWidth = mini ? 2.2 : 1.6;
        shadow(g, s, "rgba(220, 235, 255, 0.9)", 3, 0);
        for (var i = 0; i < spots.length; i++) {
            var x = spots[i][0], y = spots[i][1];
            if (mini) {
                g.beginPath();
                g.arc(x, y, r * 0.55, 0, TAU, false);
                g.fill();
                continue;
            }
            g.beginPath();
            for (var a = 0; a < 3; a++) {
                var ang = a * Math.PI / 3 + 0.3;
                g.moveTo(x - Math.cos(ang) * r, y - Math.sin(ang) * r);
                g.lineTo(x + Math.cos(ang) * r, y + Math.sin(ang) * r);
            }
            g.stroke();
        }
        g.restore();
    }

    function pellets(g, s, spots) {
        g.save();
        shadow(g, s, "rgba(20, 30, 50, 0.4)", 2, 1);
        for (var i = 0; i < spots.length; i++) {
            var x = spots[i][0], y = spots[i][1];
            var p = g.createRadialGradient(x - 1, y - 1, 0, x, y, 3.4);
            p.addColorStop(0, "#ffffff");
            p.addColorStop(1, "#c4d4e6");
            g.fillStyle = p;
            g.beginPath();
            g.arc(x, y, 3.2, 0, TAU, false);
            g.fill();
        }
        g.restore();
    }

    function bolt(g, s, x, y, k) {
        var pts = [[3, 0], [-7, 18], [0, 18], [-6, 34], [11, 12], [3, 12], [9, 0]];
        g.save();
        shadow(g, s, "rgba(255, 220, 90, 0.95)", 7, 0);
        var fill = g.createLinearGradient(0, y, 0, y + 34 * k);
        fill.addColorStop(0, "#fff8c4");
        fill.addColorStop(0.5, "#ffd62a");
        fill.addColorStop(1, "#ff9d14");
        g.fillStyle = fill;
        g.beginPath();
        for (var i = 0; i < pts.length; i++) {
            var px = x + pts[i][0] * k, py = y + pts[i][1] * k;
            if (i) g.lineTo(px, py); else g.moveTo(px, py);
        }
        g.closePath();
        g.fill();
        g.restore();
    }

    function fogBars(g, s, top, mini) {
        g.save();
        g.lineCap = "round";
        g.lineWidth = mini ? 6 : 5;
        var rows = [[12, 92, top], [20, 84, top + 8], [8, 80, top + 16], [24, 94, top + 24]];
        for (var i = 0; i < rows.length; i++) {
            var r = rows[i];
            var grad = g.createLinearGradient(r[0], 0, r[1], 0);
            grad.addColorStop(0, "rgba(255, 255, 255, 0)");
            grad.addColorStop(0.3, "rgba(240, 244, 250, 0.85)");
            grad.addColorStop(0.7, "rgba(240, 244, 250, 0.85)");
            grad.addColorStop(1, "rgba(255, 255, 255, 0)");
            g.strokeStyle = grad;
            g.beginPath();
            g.moveTo(r[0], r[2]);
            g.lineTo(r[1], r[2]);
            g.stroke();
        }
        g.restore();
    }

    // Drop and flake positions for each kind, under a cloud whose base sits near y = 46.
    var RAIN = {
        light: [[34, 50], [54, 54], [74, 50], [44, 64], [64, 66]],
        normal: [[28, 50], [44, 52], [60, 50], [76, 52], [36, 64], [52, 66], [68, 64], [84, 64]],
        mini: [[34, 50], [54, 50], [74, 50]]
    };
    var SNOW = [[30, 54], [50, 52], [70, 55], [40, 68], [60, 70], [80, 67], [24, 70]];

    function scene(g, s, kind, night, phase, mini) {
        var orb = night ? function (x, y, r) { moon(g, s, x, y, r * 0.9, phase, mini); }
                        : function (x, y, r) { sun(g, s, x, y, r, mini); };
        switch (kind) {
        case "clear":
            orb(50, 40, 22);
            break;
        case "mostlyclear":
            orb(46, 36, 21);
            cloud(g, s, 70, 58, 46, "light", mini);
            break;
        case "partlycloudy":
            orb(40, 32, 19);
            cloud(g, s, 60, 52, 68, "light", mini);
            break;
        case "overcast":
            cloud(g, s, 38, 32, 56, "mid", mini);
            cloud(g, s, 60, 50, 72, "light", mini);
            break;
        case "fog":
            cloud(g, s, 50, 30, 62, "mid", mini);
            fogBars(g, s, 50, mini);
            break;
        case "drizzle":
            cloud(g, s, 50, 30, 74, "mid", mini);
            drops(g, s, mini ? RAIN.mini : RAIN.light, 8, 0.85);
            break;
        case "lightrain":
        case "rain":
            cloud(g, s, 50, 30, 78, "dark", mini);
            drops(g, s, mini ? RAIN.mini : (kind === "rain" ? RAIN.normal : RAIN.light), 14);
            break;
        case "showers":
            orb(30, 22, 15);
            cloud(g, s, 56, 34, 72, "mid", mini);
            drops(g, s, mini ? [[42, 52], [60, 54], [78, 52]] : [[36, 54], [52, 56], [68, 54], [84, 56], [46, 68], [62, 70], [78, 68]], 12);
            break;
        case "sleet":
            cloud(g, s, 50, 30, 76, "dark", mini);
            drops(g, s, mini ? [[38, 50], [66, 52]] : [[30, 50], [54, 52], [78, 50], [42, 64], [66, 66]], 12);
            flakes(g, s, mini ? [[52, 66]] : [[42, 54], [66, 56], [30, 70], [54, 72], [78, 70]], 3.5, mini);
            break;
        case "snow":
            cloud(g, s, 50, 30, 76, "mid", mini);
            flakes(g, s, mini ? [[34, 56], [54, 60], [74, 56], [44, 72], [64, 72]] : SNOW, 4.2, mini);
            break;
        case "snowshowers":
            orb(30, 22, 15);
            cloud(g, s, 56, 34, 72, "mid", mini);
            flakes(g, s, mini ? [[44, 58], [62, 62], [80, 58]] : [[40, 58], [58, 60], [76, 58], [48, 72], [66, 74], [84, 70]], 4, mini);
            break;
        case "thunder":
        case "hail":
            cloud(g, s, 50, 28, 80, "dark", mini);
            bolt(g, s, 50, 40, mini ? 1.0 : 0.95);
            if (kind === "hail") pellets(g, s, mini ? [[30, 56], [74, 60]] : [[28, 54], [72, 52], [36, 68], [80, 66], [22, 64]]);
            else drops(g, s, mini ? [[30, 50], [76, 50]] : [[26, 50], [76, 50], [34, 64], [84, 62]], 12);
            break;
        }
    }

    // Draw the art for a weather code into a canvas, scaled so the 100 x 80 box fits its
    // height and is centred horizontally. options: {night, mini, date}.
    function draw(canvas, code, options) {
        options = options || {};
        var g = canvas.getContext("2d");
        g.clearRect(0, 0, canvas.width, canvas.height);
        if (code === null || code === undefined) return;
        var s = Math.min(canvas.height / 80, canvas.width / 100) * (options.mini ? 1.12 : 1);
        g.save();
        g.translate((canvas.width - 100 * s) / 2, (canvas.height - 80 * s) / 2);
        g.scale(s, s);
        scene(g, s, kindFor(code), !!options.night, moonPhase(options.date || new Date()), !!options.mini);
        g.restore();
    }

    // Lion's dark linen, woven from faint random threads, inside a rounded panel.
    function linen(canvas, x, y, w, h, radius) {
        var g = canvas.getContext("2d");
        g.clearRect(0, 0, canvas.width, canvas.height);
        function panel() {
            g.beginPath();
            g.moveTo(x + radius, y);
            g.arcTo(x + w, y, x + w, y + h, radius);
            g.arcTo(x + w, y + h, x, y + h, radius);
            g.arcTo(x, y + h, x, y, radius);
            g.arcTo(x, y, x + w, y, radius);
            g.closePath();
        }
        g.save();
        shadow(g, 1, "rgba(0, 0, 0, 0.6)", 9, 4);
        g.fillStyle = "#3b3c3f";
        panel();
        g.fill();
        g.restore();

        g.save();
        panel();
        g.clip();
        var seed = 7;
        function rand() {
            seed = (seed * 16807) % 2147483647;
            return seed / 2147483647;
        }
        for (var row = y; row < y + h; row++) {
            g.fillStyle = rand() < 0.5 ? "rgba(255,255,255," + (rand() * 0.06).toFixed(3) + ")"
                                       : "rgba(0,0,0," + (rand() * 0.12).toFixed(3) + ")";
            g.fillRect(x, row, w, 1);
        }
        for (var col = x; col < x + w; col++) {
            g.fillStyle = rand() < 0.5 ? "rgba(255,255,255," + (rand() * 0.05).toFixed(3) + ")"
                                       : "rgba(0,0,0," + (rand() * 0.10).toFixed(3) + ")";
            g.fillRect(col, y, 1, h);
        }
        var light = g.createRadialGradient(x + w / 2, y, 0, x + w / 2, y, w * 0.8);
        light.addColorStop(0, "rgba(255, 255, 255, 0.07)");
        light.addColorStop(1, "rgba(0, 0, 0, 0.18)");
        g.fillStyle = light;
        g.fillRect(x, y, w, h);
        g.restore();

        g.save();
        g.lineWidth = 1;
        g.strokeStyle = "rgba(255, 255, 255, 0.16)";
        x += 0.5; y += 0.5; w -= 1; h -= 1;
        panel();
        g.stroke();
        g.restore();
    }

    return { draw: draw, kindFor: kindFor, names: NAMES, linen: linen };
})();
