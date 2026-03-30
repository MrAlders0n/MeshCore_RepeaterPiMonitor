var NeighborMap = (function () {
    var map = null;
    var layerGroup = null;
    var repeaterInfo = null;
    var frozen = true;

    function init(el) {
        map = L.map(el, {
            dragging:        false,
            touchZoom:       false,
            doubleClickZoom: false,
            scrollWheelZoom: false,
            boxZoom:         false,
            keyboard:        false,
            zoomControl:     true,
        }).setView([0, 0], 2);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 19,
        }).addTo(map);
        layerGroup = L.layerGroup().addTo(map);
        return map;
    }

    function freeze() {
        if (!map) return;
        frozen = true;
        map.dragging.disable();
        map.touchZoom.disable();
        map.doubleClickZoom.disable();
        map.scrollWheelZoom.disable();
        map.boxZoom.disable();
        map.keyboard.disable();
        map.getContainer().style.cursor = 'default';
    }

    function unfreeze() {
        if (!map) return;
        frozen = false;
        map.dragging.enable();
        map.touchZoom.enable();
        map.doubleClickZoom.enable();
        map.scrollWheelZoom.enable();
        map.boxZoom.enable();
        map.keyboard.enable();
        map.getContainer().style.cursor = '';
    }

    function setRepeaterInfo(info) {
        repeaterInfo = info;
    }

    function snrColor(snr) {
        if (snr == null) return '#888';
        if (snr > 5) return '#06d6a0';
        if (snr >= -1) return '#ffa500';
        return '#ef476f';
    }

    function makeDisc(latlng, label, color, popupHtml) {
        var marker = L.circleMarker(latlng, {
            radius: 14,
            fillColor: color,
            fillOpacity: 0.85,
            color: '#fff',
            weight: 2,
        });
        marker.bindPopup(popupHtml);

        var labelIcon = L.divIcon({
            className: 'map-node-label',
            html: '<span>' + label + '</span>',
            iconSize: [40, 20],
            iconAnchor: [20, 10],
        });
        var labelMarker = L.marker(latlng, { icon: labelIcon, interactive: false });

        return [marker, labelMarker];
    }

    function update(neighbors) {
        if (!map || !layerGroup) return;
        layerGroup.clearLayers();

        var bounds = [];
        var repeaterLatLng = null;

        if (repeaterInfo && repeaterInfo.lat != null && repeaterInfo.lon != null) {
            repeaterLatLng = [repeaterInfo.lat, repeaterInfo.lon];
            var label = repeaterInfo.pubkey_prefix || '??';
            var layers = makeDisc(repeaterLatLng, label, '#00b4d8',
                '<strong>' + (repeaterInfo.name || 'Repeater') + '</strong><br>' +
                'ID: ' + label + '<br>' +
                'Role: Repeater (self)'
            );
            layers.forEach(function (l) { layerGroup.addLayer(l); });
            bounds.push(repeaterLatLng);
        }

        neighbors.forEach(function (n) {
            if (n.lat == null || n.lon == null) return;
            if (n.lat === 0 && n.lon === 0) return;

            var nLatLng = [n.lat, n.lon];
            var nLabel = (n.pubkey_prefix || '').substring(0, 4).toUpperCase();
            var ago = timeSince(n.last_seen);

            var layers = makeDisc(nLatLng, nLabel, '#06d6a0',
                '<strong>' + (n.name || n.pubkey_prefix) + '</strong><br>' +
                'ID: ' + nLabel + '<br>' +
                (n.device_role ? 'Role: ' + n.device_role + '<br>' : '') +
                'SNR: ' + (n.last_snr != null ? n.last_snr + ' dB' : '--') + '<br>' +
                'Last seen: ' + ago
            );
            layers.forEach(function (l) { layerGroup.addLayer(l); });
            bounds.push(nLatLng);

            if (repeaterLatLng) {
                var color = snrColor(n.last_snr);
                var line = L.polyline([repeaterLatLng, nLatLng], {
                    color: color,
                    weight: 2,
                    dashArray: '6, 8',
                    opacity: 0.8,
                });
                line.bindPopup(
                    (n.name || nLabel) + '<br>SNR: ' +
                    (n.last_snr != null ? n.last_snr + ' dB' : '--')
                );
                layerGroup.addLayer(line);
            }
        });

        if (bounds.length > 0) {
            map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
        }
    }

    function timeSince(epochSecs) {
        if (!epochSecs) return 'unknown';
        var diff = Math.floor(Date.now() / 1000) - epochSecs;
        if (diff < 60) return diff + 's ago';
        if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
        return Math.floor(diff / 86400) + 'd ago';
    }

    function invalidateSize() {
        if (map) map.invalidateSize();
    }

    return {
        init: init,
        freeze: freeze,
        unfreeze: unfreeze,
        setRepeaterInfo: setRepeaterInfo,
        update: update,
        invalidateSize: invalidateSize,
    };
})();
