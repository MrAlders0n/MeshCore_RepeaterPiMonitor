(function () {
    'use strict';

    var currentHours = 6;
    var refreshTimer = null;
    var REFRESH_INTERVAL = 60000;

    var activeTab = 'meshcore';
    var chartsInitialized = false;

    var piChartsInitialized = false;
    var piCurrentHours = 6;

    // ── Theme ────────────────────────────────────────────

    function getTheme() {
        var saved = localStorage.getItem('repeaterwatch-theme');
        if (saved) return saved;
        return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('repeaterwatch-theme', theme);
    }

    // ── Init Charts ──────────────────────────────────────

    function initCharts() {
        RadioChart.init(document.getElementById('chart-radio'));
        PowerCharts.init(
            document.getElementById('chart-voltage'),
            document.getElementById('chart-current'),
            document.getElementById('chart-power')
        );
        AirtimeChart.init(document.getElementById('chart-airtime'));
        PacketsChart.init(document.getElementById('chart-packets'));
        NeighborMap.init(document.getElementById('neighbor-map'));
        chartsInitialized = true;
    }

    function resizeCharts() {
        RadioChart.resize();
        PowerCharts.resize();
        AirtimeChart.resize();
        PacketsChart.resize();
        NeighborMap.invalidateSize();
    }

    // ── Pi Charts ───────────────────────────────────────

    function initPiCharts() {
        PiCpuChart.init(document.getElementById('chart-pi-cpu'));
        PiMemoryChart.init(document.getElementById('chart-pi-memory'));
        PiTempChart.init(document.getElementById('chart-pi-temp'));
        PiDiskChart.init(document.getElementById('chart-pi-disk'));
        PiDiskIoChart.init(document.getElementById('chart-pi-diskio'));
        PiNetworkChart.init(document.getElementById('chart-pi-netio'));
        piChartsInitialized = true;
    }

    function resizePiCharts() {
        PiCpuChart.resize();
        PiMemoryChart.resize();
        PiTempChart.resize();
        PiDiskChart.resize();
        PiDiskIoChart.resize();
        PiNetworkChart.resize();
    }

    function refreshPiHealth() {
        var h = piCurrentHours;

        fetchJSON('/api/v1/stats/pi/health?hours=' + h).then(function (d) {
            PiCpuChart.update(d);
            PiMemoryChart.update(d);
            PiTempChart.update(d);
            PiDiskChart.update(d);
        }).catch(function (e) { console.warn('Pi health fetch failed:', e); });

        fetchJSON('/api/v1/stats/pi/disk-io?hours=' + h).then(function (d) {
            PiDiskIoChart.update(d);
        }).catch(function (e) { console.warn('Pi disk-io fetch failed:', e); });

        fetchJSON('/api/v1/stats/pi/network-io?hours=' + h).then(function (d) {
            PiNetworkChart.update(d);
        }).catch(function (e) { console.warn('Pi network-io fetch failed:', e); });

        fetchJSON('/api/v1/stats/pi/snapshot').then(function (d) {
            updatePiStatusCards(d);
            updatePiInfoBar(d);
            renderPiProcesses(d.top_processes || []);
        }).catch(function (e) { console.warn('Pi snapshot fetch failed:', e); });

        document.getElementById('pi-last-update').textContent = 'Updated: ' + new Date().toLocaleTimeString();
    }

    function updatePiStatusCards(d) {
        document.getElementById('pi-cpu-val').textContent = (d.cpu_percent != null ? d.cpu_percent.toFixed(1) + '%' : '--%');
        document.getElementById('pi-cpu-sub').textContent = (d.per_cpu ? d.per_cpu.length + ' cores' : '-- cores');

        document.getElementById('pi-mem-val').textContent = (d.mem_percent != null ? d.mem_percent.toFixed(1) + '%' : '--%');
        document.getElementById('pi-mem-sub').textContent = (d.mem_used_mb != null ? d.mem_used_mb.toFixed(0) + ' / ' + d.mem_total_mb.toFixed(0) + ' MB' : '-- / -- MB');

        var tempEl = document.getElementById('pi-temp-val');
        if (d.cpu_temp != null) {
            tempEl.textContent = d.cpu_temp.toFixed(1) + '\u00b0C';
            tempEl.className = 'status-value';
            if (d.cpu_temp >= 80) tempEl.classList.add('temp-hot');
            else if (d.cpu_temp >= 60) tempEl.classList.add('temp-warm');
            else tempEl.classList.add('temp-cool');
        } else {
            tempEl.textContent = 'N/A';
            tempEl.className = 'status-value';
        }

        document.getElementById('pi-disk-val').textContent = (d.disk_percent != null ? d.disk_percent.toFixed(1) + '%' : '--%');
        document.getElementById('pi-disk-sub').textContent = (d.disk_used_gb != null ? d.disk_used_gb.toFixed(1) + ' / ' + d.disk_total_gb.toFixed(1) + ' GB' : '-- / -- GB');

        document.getElementById('pi-load-val').textContent = (d.load_1 != null ? d.load_1.toFixed(2) : '--');
        document.getElementById('pi-load-sub').textContent = (d.load_1 != null ? d.load_1.toFixed(2) + ' / ' + d.load_5.toFixed(2) + ' / ' + d.load_15.toFixed(2) : '1m / 5m / 15m');

        document.getElementById('pi-uptime-val').textContent = formatUptime(d.uptime_secs);
        document.getElementById('pi-uptime-sub').textContent = (d.process_count != null ? d.process_count + ' processes' : '-- processes');
    }

    function updatePiInfoBar(d) {
        var p = d.platform || {};
        document.getElementById('pi-hostname').textContent = p.hostname || p.node || '--';
        document.getElementById('pi-os-version').textContent = (p.system || '--') + ' ' + (p.release || '');
        document.getElementById('pi-model').textContent = p.machine || '--';
    }

    function renderPiProcesses(procs) {
        var tbody = document.getElementById('pi-processes-tbody');
        tbody.innerHTML = '';
        procs.forEach(function (p) {
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td>' + p.pid + '</td>' +
                '<td>' + (p.name || '--') + '</td>' +
                '<td>' + p.cpu_percent.toFixed(1) + '</td>' +
                '<td>' + p.memory_percent.toFixed(1) + '</td>';
            tbody.appendChild(tr);
        });
    }

    function setupPiTimeButtons() {
        var buttons = document.querySelectorAll('.pi-time-btn');
        buttons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                buttons.forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                piCurrentHours = parseInt(btn.getAttribute('data-hours'), 10);
                refreshPiHealth();
            });
        });
    }

    // ── Tabs ─────────────────────────────────────────────

    function setupTabs() {
        var tabBtns = document.querySelectorAll('.tab-btn');
        tabBtns.forEach(function (btn) {
            btn.addEventListener('click', function () {
                var tabId = btn.getAttribute('data-tab');
                if (tabId === activeTab) return;

                // Update button states
                tabBtns.forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');

                // Update panel states
                document.querySelectorAll('.tab-panel').forEach(function (p) {
                    p.classList.remove('active');
                });
                document.getElementById('tab-' + tabId).classList.add('active');

                activeTab = tabId;
                onTabActivated(tabId);
            });
        });
    }

    function onTabActivated(tabId) {
        if (tabId === 'meshcore') {
            if (!chartsInitialized) {
                initCharts();
            }
            setTimeout(function () {
                resizeCharts();
            }, 50);
            refreshMeshCore();
            stopServicesRefresh();
        } else if (tabId === 'raspberry-pi') {
            if (!piChartsInitialized) {
                initPiCharts();
            }
            setTimeout(function () {
                resizePiCharts();
            }, 50);
            refreshPiHealth();
            stopServicesRefresh();
        } else if (tabId === 'tools') {
            startServicesRefresh();
        }
    }

    // ── API Fetchers ─────────────────────────────────────

    function fetchJSON(url) {
        return fetch(url).then(function (r) {
            if (r.status === 401) {
                window.location.href = '/login';
                throw new Error('Unauthorized');
            }
            if (!r.ok) throw new Error(r.status);
            return r.json();
        });
    }

    function refreshHeader() {
        fetchJSON('/api/v1/status').then(function (d) {
            var dot = document.getElementById('status-dot');
            dot.classList.toggle('connected', d.serial_connected);
            dot.title = d.serial_connected ? 'Connected to ' + d.serial_port : 'Disconnected';
            document.getElementById('footer-queue').textContent = '--';
            document.getElementById('footer-errors').textContent = d.error_count || 0;
            document.getElementById('footer-db-size').textContent = formatBytes(d.db_size_bytes);
            document.getElementById('footer-polls').textContent = d.poll_count || 0;
        }).catch(noop);
    }

    function refreshMeshCore() {
        var h = currentHours;

        fetchJSON('/api/v1/device').then(function (d) {
            document.getElementById('mc-radio-name').textContent = d.name || '--';
            document.getElementById('mc-firmware').textContent = d.firmware || '--';
            document.getElementById('mc-board').textContent = d.board || '--';
            document.getElementById('mc-radio-config').textContent = d.radio_config || '';
            document.getElementById('mc-uptime-val').textContent = formatUptime(d.uptime_secs);
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
            updateMeshCoreStatusCards(d);
        }).catch(noop);

        var neighborsReady = fetchJSON('/api/v1/neighbors').then(function (d) {
            renderNeighborsTable(d);
            return d;
        }).catch(function () { return []; });

        neighborsReady.then(function (neighbors) {
            NeighborMap.update(neighbors);
        });

        fetchJSON('/api/v1/packets/recent?limit=50').then(function (d) {
            renderPacketsTable(d);
        }).catch(noop);

        document.getElementById('last-update').textContent = 'Updated: ' + new Date().toLocaleTimeString();
    }

    function updateMeshCoreStatusCards(d) {
        if (!d.timestamps || !d.timestamps.length) return;
        var txDirect = 0, txFlood = 0, rxDirect = 0, rxFlood = 0, rxErrors = 0;
        for (var i = 0; i < d.timestamps.length; i++) {
            txDirect += d.tx_direct[i] || 0;
            txFlood += d.tx_flood[i] || 0;
            rxDirect += d.rx_direct[i] || 0;
            rxFlood += d.rx_flood[i] || 0;
            rxErrors += d.rx_errors[i] || 0;
        }
        document.getElementById('mc-tx-val').textContent = (txDirect + txFlood).toLocaleString();
        document.getElementById('mc-tx-sub').textContent = txDirect + ' direct / ' + txFlood + ' flood';
        document.getElementById('mc-rx-val').textContent = (rxDirect + rxFlood).toLocaleString();
        document.getElementById('mc-rx-sub').textContent = rxDirect + ' direct / ' + rxFlood + ' flood';
        document.getElementById('mc-err-val').textContent = rxErrors.toLocaleString();
    }

    function refreshAll() {
        refreshHeader();
        if (activeTab === 'meshcore') {
            refreshMeshCore();
        } else if (activeTab === 'raspberry-pi') {
            refreshPiHealth();
        }
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

    function copyText(text) {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
    }

    function renderPacketsTable(packets) {
        var tbody = document.getElementById('packets-tbody');
        tbody.innerHTML = '';
        packets.forEach(function (p) {
            var tr = document.createElement('tr');
            var raw = p.raw_hex || '';
            var display = raw.length > 20 ? raw.substring(0, 20) + '...' : (raw || '--');
            tr.innerHTML =
                '<td>' + formatTime(p.ts) + '</td>' +
                '<td class="dir-' + (p.direction || '').toLowerCase() + '">' + (p.direction || '--') + '</td>' +
                '<td>' + (PKT_TYPES[p.pkt_type] || p.pkt_type || '--') + '</td>' +
                '<td>' + (ROUTE_NAMES[p.route] || p.route || '--') + '</td>' +
                '<td>' + (p.snr != null ? p.snr.toFixed(1) : '--') + '</td>' +
                '<td>' + (p.rssi != null ? p.rssi.toFixed(0) : '--') + '</td>' +
                '<td>' + (p.score != null ? p.score.toFixed(2) : '--') + '</td>' +
                '<td class="pkt-hex" data-raw="' + raw + '" title="Click to copy full packet">' + display + '</td>';
            tbody.appendChild(tr);
        });

        tbody.addEventListener('click', function (e) {
            var cell = e.target.closest('.pkt-hex');
            if (!cell) return;
            var full = cell.getAttribute('data-raw');
            if (!full) return;
            var saved = cell.textContent;
            copyText(full);
            cell.textContent = 'Copied!';
            setTimeout(function () { cell.textContent = saved; }, 1000);
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
        var buttons = document.querySelectorAll('#time-controls .time-btn');
        buttons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                buttons.forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                currentHours = parseInt(btn.getAttribute('data-hours'), 10);
                refreshMeshCore();
            });
        });
    }

    function setupThemeToggle() {
        document.getElementById('theme-toggle').addEventListener('click', function () {
            var next = getTheme() === 'dark' ? 'light' : 'dark';
            applyTheme(next);
            if (activeTab === 'meshcore') {
                initCharts();
                refreshMeshCore();
                piChartsInitialized = false;
            } else if (activeTab === 'raspberry-pi') {
                initPiCharts();
                refreshPiHealth();
                chartsInitialized = false;
            } else {
                chartsInitialized = false;
                piChartsInitialized = false;
            }
        });
    }

    function setupMapFullscreen() {
        var card = document.getElementById('map-card');
        var btn = document.getElementById('map-fullscreen');
        btn.addEventListener('click', function () {
            card.classList.toggle('fullscreen');
            btn.textContent = card.classList.contains('fullscreen') ? '\u2715' : '\u26F6';
            setTimeout(function () { NeighborMap.invalidateSize(); }, 100);
        });
    }

    // ── Firmware Flash ────────────────────────────────────

    var fwPollTimer = null;

    function setupFirmwareFlash() {
        var fileInput = document.getElementById('fw-file');
        var fileLabel = document.getElementById('fw-file-name');
        var hashInput = document.getElementById('fw-sha256');
        var flashBtn = document.getElementById('fw-flash-btn');

        fileInput.addEventListener('change', function () {
            if (fileInput.files.length > 0) {
                fileLabel.textContent = fileInput.files[0].name;
            } else {
                fileLabel.textContent = 'Choose firmware .zip';
            }
            updateFlashBtn();
        });

        hashInput.addEventListener('input', updateFlashBtn);

        function updateFlashBtn() {
            var hasFile = fileInput.files.length > 0;
            var hasHash = hashInput.value.trim().length === 64;
            flashBtn.disabled = !(hasFile && hasHash);
        }

        flashBtn.addEventListener('click', function () {
            if (!confirm('Are you sure you want to flash firmware? This will temporarily stop all services.')) {
                return;
            }
            var formData = new FormData();
            formData.append('firmware', fileInput.files[0]);
            formData.append('sha256', hashInput.value.trim());

            flashBtn.disabled = true;
            showFwStatus('flashing', 'Uploading firmware...');
            showFwLog('');

            fetch('/api/v1/firmware/flash', { method: 'POST', body: formData })
                .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
                .then(function (resp) {
                    if (!resp.ok) {
                        showFwStatus('error', resp.data.error || 'Upload failed');
                        flashBtn.disabled = false;
                        return;
                    }
                    startFwPolling();
                })
                .catch(function (err) {
                    showFwStatus('error', 'Network error: ' + err.message);
                    flashBtn.disabled = false;
                });
        });
    }

    // ── Services & Reboot Pi ─────────────────────────────

    var servicesTimer = null;

    function setupServices() {
        document.querySelectorAll('.restart-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var name = btn.getAttribute('data-service');
                if (!confirm('Restart service "' + name + '"?')) return;
                btn.disabled = true;
                btn.textContent = 'Restarting...';
                fetch('/api/v1/services/' + encodeURIComponent(name) + '/restart', { method: 'POST' })
                    .then(function (r) { return r.json(); })
                    .then(function () {
                        btn.textContent = 'Restarted';
                        setTimeout(function () {
                            btn.textContent = 'Restart';
                            btn.disabled = false;
                            refreshServices();
                        }, 3000);
                    })
                    .catch(function () {
                        btn.textContent = 'Error';
                        setTimeout(function () {
                            btn.textContent = 'Restart';
                            btn.disabled = false;
                        }, 3000);
                    });
            });
        });

        document.getElementById('reboot-pi-btn').addEventListener('click', function () {
            if (!confirm('Reboot the Raspberry Pi? All services will go down.')) return;
            var btn = this;
            btn.disabled = true;
            btn.textContent = 'Rebooting...';
            fetch('/api/v1/system/reboot', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .catch(noop);
        });
    }

    function setupRebootRadio() {
        document.getElementById('reboot-radio-btn').addEventListener('click', function () {
            alert('Reboot Radio is not yet implemented. A relay-based hard reboot will be added in a future update.');
        });
    }

    function refreshServices() {
        fetchJSON('/api/v1/services').then(function (services) {
            services.forEach(function (svc) {
                var row = document.querySelector('.service-row[data-service="' + svc.name + '"]');
                if (!row) return;
                var dot = row.querySelector('.service-dot');
                var uptimeEl = row.querySelector('.service-uptime');
                dot.classList.toggle('active', svc.active);
                dot.classList.toggle('inactive', !svc.active);
                if (svc.active && svc.uptime_secs != null) {
                    uptimeEl.textContent = formatUptime(svc.uptime_secs);
                } else {
                    uptimeEl.textContent = svc.active ? '--' : 'stopped';
                }
            });
        }).catch(function (e) { console.warn('Services fetch failed:', e); });
    }

    function startServicesRefresh() {
        refreshServices();
        if (servicesTimer) clearInterval(servicesTimer);
        servicesTimer = setInterval(refreshServices, 30000);
    }

    function stopServicesRefresh() {
        if (servicesTimer) {
            clearInterval(servicesTimer);
            servicesTimer = null;
        }
    }

    function startFwPolling() {
        if (fwPollTimer) clearInterval(fwPollTimer);
        fwPollTimer = setInterval(pollFwStatus, 2000);
        pollFwStatus();
    }

    function pollFwStatus() {
        fetchJSON('/api/v1/firmware/status').then(function (d) {
            showFwStatus(d.state, d.progress);
            if (d.log && d.log.length > 0) {
                showFwLog(d.log.join('\n'));
            }
            if (d.state === 'done' || d.state === 'error' || d.state === 'idle') {
                if (fwPollTimer) {
                    clearInterval(fwPollTimer);
                    fwPollTimer = null;
                }
                document.getElementById('fw-sha256').value = '';
                document.getElementById('fw-flash-btn').disabled = true;
            }
        }).catch(noop);
    }

    function showFwStatus(state, text) {
        var el = document.getElementById('fw-status');
        var span = document.getElementById('fw-status-text');
        el.style.display = text ? 'block' : 'none';
        el.className = 'fw-status state-' + state;
        span.textContent = text;
    }

    function showFwLog(text) {
        var el = document.getElementById('fw-log');
        el.style.display = text ? 'block' : 'none';
        el.textContent = text;
        el.scrollTop = el.scrollHeight;
    }

    // ── Terminal ───────────────────────────────────────────

    var terminalInstance = null;
    var terminalWs = null;
    var terminalFitAddon = null;
    var terminalMode = 'pty';
    var terminalConnected = false;

    function setupTerminal() {
        var modeBtns = document.querySelectorAll('.terminal-mode-btn');
        var connectBtn = document.getElementById('terminal-connect-btn');

        modeBtns.forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (terminalConnected) return;
                modeBtns.forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                terminalMode = btn.getAttribute('data-mode');
            });
        });

        connectBtn.addEventListener('click', function () {
            if (terminalConnected) {
                disconnectTerminal();
            } else {
                connectTerminal();
            }
        });
    }

    function connectTerminal() {
        var container = document.getElementById('terminal-container');
        var termEl = document.getElementById('xterm-terminal');
        var connectBtn = document.getElementById('terminal-connect-btn');
        var statusEl = document.getElementById('terminal-status');
        var modeBtns = document.querySelectorAll('.terminal-mode-btn');

        container.style.display = 'block';

        if (terminalInstance) {
            terminalInstance.dispose();
            terminalInstance = null;
        }
        termEl.innerHTML = '';

        terminalInstance = new Terminal({
            cursorBlink: true,
            fontSize: 14,
            fontFamily: '"Cascadia Code", "Fira Code", "Source Code Pro", monospace',
            theme: {
                background: '#000000',
                foreground: '#e0e0e0'
            }
        });

        terminalFitAddon = new FitAddon.FitAddon();
        terminalInstance.loadAddon(terminalFitAddon);

        if (typeof WebLinksAddon !== 'undefined') {
            terminalInstance.loadAddon(new WebLinksAddon.WebLinksAddon());
        }

        terminalInstance.open(termEl);
        terminalFitAddon.fit();

        var wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        var wsPath = terminalMode === 'pty' ? '/ws/terminal/pty' : '/ws/terminal/serial';
        var wsUrl = wsProtocol + '//' + window.location.host + wsPath;

        terminalWs = new WebSocket(wsUrl);
        terminalWs.binaryType = 'arraybuffer';

        terminalWs.onopen = function () {
            terminalConnected = true;
            connectBtn.textContent = 'Disconnect';
            connectBtn.classList.add('connected');
            statusEl.textContent = 'Connected (' + (terminalMode === 'pty' ? 'Pi Console' : 'Serial ttyV2') + ')';
            statusEl.className = 'terminal-status connected';
            modeBtns.forEach(function (b) { b.disabled = true; });
            terminalInstance.focus();
        };

        terminalWs.onmessage = function (ev) {
            if (ev.data instanceof ArrayBuffer) {
                terminalInstance.write(new Uint8Array(ev.data));
            } else {
                terminalInstance.write(ev.data);
            }
        };

        terminalWs.onclose = function () {
            terminalConnected = false;
            connectBtn.textContent = 'Connect';
            connectBtn.classList.remove('connected');
            statusEl.textContent = 'Disconnected';
            statusEl.className = 'terminal-status';
            modeBtns.forEach(function (b) { b.disabled = false; });
        };

        terminalWs.onerror = function () {
            statusEl.textContent = 'Connection error';
            statusEl.className = 'terminal-status error';
        };

        terminalInstance.onData(function (data) {
            if (terminalWs && terminalWs.readyState === WebSocket.OPEN) {
                terminalWs.send(data);
            }
        });
    }

    function disconnectTerminal() {
        if (terminalWs) {
            terminalWs.close();
            terminalWs = null;
        }
    }

    // ── Resize ───────────────────────────────────────────

    var resizeTimeout;
    window.addEventListener('resize', function () {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(function () {
            if (activeTab === 'meshcore' && chartsInitialized) {
                resizeCharts();
            }
            if (activeTab === 'raspberry-pi' && piChartsInitialized) {
                resizePiCharts();
            }
            if (terminalConnected && terminalFitAddon) {
                terminalFitAddon.fit();
            }
        }, 200);
    });

    // ── Boot ─────────────────────────────────────────────

    applyTheme(getTheme());
    setupTabs();
    initCharts();
    refreshAll();
    setupTimeButtons();
    setupPiTimeButtons();
    setupThemeToggle();
    setupMapFullscreen();
    setupFirmwareFlash();
    setupRebootRadio();
    setupServices();
    setupTerminal();

    refreshTimer = setInterval(refreshAll, REFRESH_INTERVAL);
})();
