(function () {
    'use strict';

    var currentHours = 6;
    var refreshTimer = null;
    var REFRESH_INTERVAL = 60000;

    // ── Theme ────────────────────────────────────────────

    function getTheme() {
        var saved = localStorage.getItem('meshcore-theme');
        if (saved) return saved;
        return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('meshcore-theme', theme);
    }

    function echartsTheme() {
        return getTheme() === 'dark' ? 'dark' : null;
    }

    // ── Init Charts ──────────────────────────────────────

    function initCharts() {
        var theme = echartsTheme();
        RadioChart.init(document.getElementById('chart-radio'), theme);
        PowerCharts.init(
            document.getElementById('chart-voltage'),
            document.getElementById('chart-current'),
            document.getElementById('chart-power'),
            theme
        );
        AirtimeChart.init(document.getElementById('chart-airtime'), theme);
        PacketsChart.init(document.getElementById('chart-packets'), theme);
        NeighborMap.init(document.getElementById('neighbor-map'));
    }

    // ── API Fetchers ─────────────────────────────────────

    function fetchJSON(url) {
        return fetch(url).then(function (r) {
            if (!r.ok) throw new Error(r.status);
            return r.json();
        });
    }

    function refreshAll() {
        var h = currentHours;

        fetchJSON('/api/v1/device').then(function (d) {
            document.getElementById('device-name').textContent = d.name || 'MeshCore Repeater';
            document.getElementById('firmware-badge').textContent = d.firmware || '--';
            document.getElementById('board-badge').textContent = d.board || '--';
            document.getElementById('uptime-display').textContent = 'Uptime: ' + formatUptime(d.uptime_secs);
            NeighborMap.setRepeaterInfo(d);
        }).catch(noop);

        fetchJSON('/api/v1/stats/power?hours=' + h).then(function (d) {
            PowerCharts.update(d);
        }).catch(noop);

        fetchJSON('/api/v1/stats/radio?hours=' + h).then(function (d) {
            RadioChart.update(d);
        }).catch(noop);

        fetchJSON('/api/v1/stats/airtime?hours=' + h).then(function (d) {
            AirtimeChart.update(d);
        }).catch(noop);

        fetchJSON('/api/v1/packets/activity?hours=' + h + '&bucket_minutes=' + bucketForHours(h)).then(function (d) {
            PacketsChart.update(d);
        }).catch(noop);

        fetchJSON('/api/v1/neighbors').then(function (d) {
            NeighborMap.update(d);
            renderNeighborsTable(d);
        }).catch(noop);

        fetchJSON('/api/v1/packets/recent?limit=50').then(function (d) {
            renderPacketsTable(d);
        }).catch(noop);

        fetchJSON('/api/v1/status').then(function (d) {
            var dot = document.getElementById('status-dot');
            dot.classList.toggle('connected', d.serial_connected);
            dot.title = d.serial_connected ? 'Connected to ' + d.serial_port : 'Disconnected';
            document.getElementById('footer-queue').textContent = '--';
            document.getElementById('footer-errors').textContent = d.error_count || 0;
            document.getElementById('footer-db-size').textContent = formatBytes(d.db_size_bytes);
            document.getElementById('footer-polls').textContent = d.poll_count || 0;
        }).catch(noop);

        document.getElementById('last-update').textContent = 'Updated: ' + new Date().toLocaleTimeString();
    }

    function bucketForHours(h) {
        if (h <= 1) return 5;
        if (h <= 6) return 15;
        if (h <= 24) return 30;
        if (h <= 168) return 120;
        return 360;
    }

    // ── Neighbors Table ─────────────────────────────────

    function renderNeighborsTable(neighbors) {
        var tbody = document.getElementById('neighbors-tbody');
        tbody.innerHTML = '';
        neighbors.forEach(function (n) {
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td>' + (n.name || n.pubkey_prefix || '--') + '</td>' +
                '<td>' + (n.device_role || '--') + '</td>' +
                '<td>' + fmtSnr(n.last_snr) + '</td>' +
                '<td>' + fmtRssi(n.last_rssi) + '</td>' +
                '<td>' + fmtSnr(n.avg_snr) + '</td>' +
                '<td>' + fmtRssi(n.avg_rssi) + '</td>' +
                '<td>' + timeSince(n.last_seen) + '</td>';
            tbody.appendChild(tr);
        });
    }

    function fmtSnr(v) {
        if (v == null) return '--';
        var cls = v > 5 ? 'snr-good' : v >= -1 ? 'snr-ok' : 'snr-bad';
        return '<span class="' + cls + '">' + v.toFixed(1) + '</span>';
    }

    function fmtRssi(v) {
        return v != null ? v.toFixed(0) + ' dBm' : '--';
    }

    function timeSince(epochSecs) {
        if (!epochSecs) return '--';
        var diff = Math.floor(Date.now() / 1000) - epochSecs;
        if (diff < 60) return diff + 's ago';
        if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
        return Math.floor(diff / 86400) + 'd ago';
    }

    // ── Packets Table ────────────────────────────────────

    var PKT_TYPES = {
        0: 'Request', 1: 'Response', 2: 'TxtMsg', 3: 'Ack',
        4: 'Advert', 5: 'GrpTxt', 6: 'GrpData', 7: 'AnonReq',
        8: 'Path', 9: 'Trace', 10: 'Multipart', 11: 'Control',
        15: 'RawCustom'
    };
    var ROUTE_NAMES = {'D': 'Direct', 'F': 'Flood', 'TD': 'T.Direct', 'TF': 'T.Flood'};

    function renderPacketsTable(packets) {
        var tbody = document.getElementById('packets-tbody');
        tbody.innerHTML = '';
        packets.forEach(function (p) {
            var tr = document.createElement('tr');
            var raw = p.raw_hex || p.hash || '--';
            var truncated = raw.length > 16 ? raw.substring(0, 16) + '...' : raw;
            tr.innerHTML =
                '<td>' + formatTime(p.ts) + '</td>' +
                '<td class="dir-' + (p.direction || '').toLowerCase() + '">' + (p.direction || '--') + '</td>' +
                '<td>' + (PKT_TYPES[p.pkt_type] || p.pkt_type || '--') + '</td>' +
                '<td>' + (ROUTE_NAMES[p.route] || p.route || '--') + '</td>' +
                '<td>' + (p.snr != null ? p.snr.toFixed(1) : '--') + '</td>' +
                '<td>' + (p.rssi != null ? p.rssi.toFixed(0) : '--') + '</td>' +
                '<td>' + (p.score != null ? p.score.toFixed(2) : '--') + '</td>' +
                '<td class="pkt-hex" title="Click to copy">' + truncated + '</td>';
            if (raw !== '--') {
                tr.querySelector('.pkt-hex').addEventListener('click', function () {
                    navigator.clipboard.writeText(raw).then(function () {
                        var cell = tr.querySelector('.pkt-hex');
                        cell.textContent = 'Copied!';
                        setTimeout(function () { cell.textContent = truncated; }, 1000);
                    });
                });
            }
            tbody.appendChild(tr);
        });
    }

    // ── Formatters ───────────────────────────────────────

    function formatUptime(secs) {
        if (secs == null) return '--';
        var d = Math.floor(secs / 86400);
        var h = Math.floor((secs % 86400) / 3600);
        var m = Math.floor((secs % 3600) / 60);
        if (d > 0) return d + 'd ' + h + 'h';
        if (h > 0) return h + 'h ' + m + 'm';
        return m + 'm';
    }

    function formatTime(epoch) {
        if (!epoch) return '--';
        return new Date(epoch * 1000).toLocaleTimeString();
    }

    function formatBytes(bytes) {
        if (bytes == null) return '--';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / 1048576).toFixed(1) + ' MB';
    }

    function noop() {}

    // ── Event Handlers ───────────────────────────────────

    function setupTimeButtons() {
        var buttons = document.querySelectorAll('.time-btn');
        buttons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                buttons.forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                currentHours = parseInt(btn.getAttribute('data-hours'), 10);
                refreshAll();
            });
        });
    }

    function setupThemeToggle() {
        document.getElementById('theme-toggle').addEventListener('click', function () {
            var next = getTheme() === 'dark' ? 'light' : 'dark';
            applyTheme(next);
            initCharts();
            refreshAll();
        });
    }

    // ── Resize ───────────────────────────────────────────

    var resizeTimeout;
    window.addEventListener('resize', function () {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(function () {
            RadioChart.resize();
            PowerCharts.resize();
            AirtimeChart.resize();
            PacketsChart.resize();
            NeighborMap.invalidateSize();
        }, 200);
    });

    // ── Boot ─────────────────────────────────────────────

    applyTheme(getTheme());
    initCharts();
    refreshAll();
    setupTimeButtons();
    setupThemeToggle();

    refreshTimer = setInterval(refreshAll, REFRESH_INTERVAL);
})();
