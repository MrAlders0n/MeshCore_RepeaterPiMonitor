/**
 * sensors_manage.js
 * Handles sensor config modal and dynamic section visibility.
 * Deploy to: /opt/RepeaterWatch/static/js/sensors_manage.js
 */

(function () {
    'use strict';

    var SENSOR_SECTIONS = {
        ina3221:  'sensor-section-ina3221',
        bme280:   'sensor-section-bme280',
        lis2dw12: 'sensor-section-lis2dw12',
        bq24074:  'sensor-section-bq24074',
        as3935:   'sensor-section-as3935',
    };

    var _config = {};

    function fetchJSON(url, opts) {
        return fetch(url, opts).then(function (r) { return r.json(); });
    }

    function el(id) { return document.getElementById(id); }

    function applyConfig(cfg, pollingEnabled) {
        _config = cfg || {};

        var enabledCount = 0;
        Object.keys(SENSOR_SECTIONS).forEach(function (name) {
            var sectionEl = el(SENSOR_SECTIONS[name]);
            if (!sectionEl) return;
            var enabled = !!_config[name];
            sectionEl.style.display = enabled ? '' : 'none';
            if (enabled) enabledCount++;
        });

        var badge = el('sensor-poll-status');
        if (badge) {
            badge.textContent = pollingEnabled ? 'Polling On' : 'Polling Off';
            badge.className = 'sensor-poll-badge ' + (pollingEnabled ? 'sensor-poll-on' : 'sensor-poll-off');
        }

        var countEl = el('sensor-active-count');
        if (countEl) {
            if (enabledCount === 0) {
                countEl.textContent = 'No sensors enabled';
            } else {
                countEl.textContent = enabledCount + ' sensor' + (enabledCount === 1 ? '' : 's') + ' enabled';
            }
        }

        var emptyState = el('sensor-empty-state');
        var timeNav    = el('sensor-time-nav');
        if (emptyState) emptyState.style.display = enabledCount === 0 ? '' : 'none';
        if (timeNav)    timeNav.style.display    = enabledCount === 0 ? 'none' : '';
    }

    function loadSensorConfig() {
        fetchJSON('/api/v1/sensors/config')
            .then(function (data) {
                applyConfig(data.sensors || {}, data.polling_enabled || false);
            })
            .catch(function (err) {
                console.warn('sensors_manage: could not load sensor config', err);
                applyConfig({}, false);
            });
    }

    function openModal() {
        Object.keys(SENSOR_SECTIONS).forEach(function (name) {
            var cb = el('sensor-toggle-' + name);
            if (cb) cb.checked = !!_config[name];
        });

        var statusEl   = el('sensor-save-status');
        var restartBtn = el('sensor-restart-btn');
        if (statusEl)   { statusEl.textContent = ''; statusEl.className = 'sensor-save-status'; }
        if (restartBtn) restartBtn.style.display = 'none';

        var overlay = el('sensor-modal-overlay');
        if (overlay) overlay.style.display = '';
    }

    function closeModal() {
        var overlay = el('sensor-modal-overlay');
        if (overlay) overlay.style.display = 'none';
    }

    function saveConfig() {
        var saveBtn    = el('sensor-save-btn');
        var statusEl   = el('sensor-save-status');
        var restartBtn = el('sensor-restart-btn');

        var sensors = {};
        Object.keys(SENSOR_SECTIONS).forEach(function (name) {
            var cb = el('sensor-toggle-' + name);
            sensors[name] = cb ? cb.checked : false;
        });

        if (saveBtn) saveBtn.disabled = true;
        if (statusEl) { statusEl.textContent = 'Saving...'; statusEl.className = 'sensor-save-status'; }

        fetchJSON('/api/v1/sensors/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sensors: sensors })
        })
        .then(function (data) {
            if (data.ok) {
                if (statusEl)   { statusEl.textContent = 'Saved.'; statusEl.className = 'sensor-save-status success'; }
                if (restartBtn) restartBtn.style.display = '';
                applyConfig(sensors, data.polling_enabled || false);
                window.dispatchEvent(new CustomEvent('sensorConfigChanged', { detail: sensors }));
            } else {
                throw new Error(data.error || 'Save failed');
            }
        })
        .catch(function (err) {
            if (statusEl) { statusEl.textContent = 'Error: ' + err.message; statusEl.className = 'sensor-save-status error'; }
        })
        .finally(function () {
            if (saveBtn) saveBtn.disabled = false;
        });
    }

    function restartService() {
        var restartBtn = el('sensor-restart-btn');
        var statusEl   = el('sensor-save-status');
        if (restartBtn) restartBtn.disabled = true;
        if (statusEl)   { statusEl.textContent = 'Restarting...'; statusEl.className = 'sensor-save-status'; }

        fetchJSON('/api/v1/services/RepeaterWatch/restart', { method: 'POST' })
            .then(function () {
                if (statusEl) statusEl.textContent = 'Restarting... page will reload in 5s';
                setTimeout(function () { window.location.reload(); }, 5000);
            })
            .catch(function (err) {
                if (statusEl) { statusEl.textContent = 'Restart failed: ' + err.message; statusEl.className = 'sensor-save-status error'; }
                if (restartBtn) restartBtn.disabled = false;
            });
    }

    function init() {
        var manageBtn  = el('sensor-manage-btn');
        var closeBtn   = el('sensor-modal-close');
        var overlay    = el('sensor-modal-overlay');
        var saveBtn    = el('sensor-save-btn');
        var restartBtn = el('sensor-restart-btn');

        if (manageBtn)  manageBtn.addEventListener('click', openModal);
        if (closeBtn)   closeBtn.addEventListener('click', closeModal);
        if (saveBtn)    saveBtn.addEventListener('click', saveConfig);
        if (restartBtn) restartBtn.addEventListener('click', restartService);

        if (overlay) {
            overlay.addEventListener('click', function (e) {
                if (e.target === overlay) closeModal();
            });
        }

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && overlay && overlay.style.display !== 'none') closeModal();
        });

        loadSensorConfig();

        document.querySelectorAll('.tab-btn[data-tab="sensors"]').forEach(function (btn) {
            btn.addEventListener('click', loadSensorConfig);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.sensorManage = {
        getConfig: function () { return Object.assign({}, _config); },
        reload: loadSensorConfig
    };

})();
