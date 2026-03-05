var SensorCharts = (function () {
    var charts = {};

    var TT = { trigger: 'axis', backgroundColor: 'rgba(30,30,50,0.95)', borderColor: '#555', textStyle: { color: '#e0e0e0' } };
    var AX = { axisLine: { lineStyle: { color: '#888' } }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } } };

    function makeOption(yName, seriesDefs) {
        var series = seriesDefs.map(function (s) {
            return {
                name: s.name,
                type: 'line',
                smooth: true,
                symbol: 'none',
                lineStyle: { width: 2, color: s.color },
                itemStyle: { color: s.color },
                areaStyle: s.area ? { color: s.area } : undefined,
                data: [],
            };
        });
        return {
            backgroundColor: 'transparent',
            tooltip: TT,
            legend: seriesDefs.length > 1 ? {
                data: seriesDefs.map(function (s) { return s.name; }),
                textStyle: { fontSize: 11, color: '#aaa' },
                top: 0,
            } : undefined,
            xAxis: { type: 'time', axisLine: AX.axisLine },
            yAxis: {
                type: 'value', name: yName,
                nameTextStyle: { color: '#888' },
                axisLine: AX.axisLine, splitLine: AX.splitLine,
            },
            dataZoom: [
                { type: 'inside', xAxisIndex: 0 },
                { type: 'slider', xAxisIndex: 0, height: 20, bottom: 5 },
            ],
            series: series,
            grid: { left: 50, right: 16, top: 30, bottom: 50 },
        };
    }

    function init(elements) {
        // Battery Voltage (Ch0)
        charts.battVolt = echarts.init(elements.battVolt);
        charts.battVolt.setOption(makeOption('V', [
            { name: 'Battery V', color: '#06d6a0', area: 'rgba(6,214,160,0.1)' },
        ]));
        // Add voltage zone markAreas
        charts.battVolt.setOption({
            series: [{
                markArea: {
                    silent: true,
                    data: [
                        [{ yAxis: 0, itemStyle: { color: 'rgba(239,71,111,0.08)' } }, { yAxis: 3.3 }],
                        [{ yAxis: 3.3, itemStyle: { color: 'rgba(255,209,102,0.08)' } }, { yAxis: 3.6 }],
                        [{ yAxis: 3.6, itemStyle: { color: 'rgba(6,214,160,0.05)' } }, { yAxis: 4.5 }],
                    ],
                },
            }],
            yAxis: { min: 3.0, max: 4.2 },
        });

        // Battery Current (Ch0)
        charts.battCurr = echarts.init(elements.battCurr);
        charts.battCurr.setOption(makeOption('mA', [
            { name: 'Battery mA', color: '#00b4d8' },
        ]));
        charts.battCurr.setOption({
            series: [{
                markLine: {
                    silent: true,
                    data: [{ yAxis: 0, lineStyle: { color: '#555', type: 'dashed' } }],
                    label: { show: false },
                    symbol: 'none',
                },
            }],
        });

        // Load Voltage (Ch1)
        charts.loadVolt = echarts.init(elements.loadVolt);
        charts.loadVolt.setOption(makeOption('V', [
            { name: 'Load V', color: '#ffd166', area: 'rgba(255,209,102,0.1)' },
        ]));

        // Load Current (Ch1)
        charts.loadCurr = echarts.init(elements.loadCurr);
        charts.loadCurr.setOption(makeOption('mA', [
            { name: 'Load mA', color: '#ef476f' },
        ]));

        // Temperature
        charts.temp = echarts.init(elements.temp);
        charts.temp.setOption(makeOption('\u00B0C', [
            { name: 'Temperature', color: '#ff6b6b', area: 'rgba(255,107,107,0.08)' },
        ]));
        charts.temp.setOption({
            series: [{
                markArea: {
                    silent: true,
                    data: [
                        [{ yAxis: 60, itemStyle: { color: 'rgba(239,71,111,0.12)' } }, { yAxis: 100 }],
                        [{ yAxis: -40, itemStyle: { color: 'rgba(0,180,216,0.12)' } }, { yAxis: -20 }],
                    ],
                },
            }],
        });

        // Humidity
        charts.humidity = echarts.init(elements.humidity);
        charts.humidity.setOption(makeOption('%', [
            { name: 'Humidity', color: '#48bfe3', area: 'rgba(72,191,227,0.08)' },
        ]));
        charts.humidity.setOption({
            series: [{
                markArea: {
                    silent: true,
                    data: [
                        [{ yAxis: 80, itemStyle: { color: 'rgba(255,209,102,0.1)' } }, { yAxis: 90 }],
                        [{ yAxis: 90, itemStyle: { color: 'rgba(239,71,111,0.12)' } }, { yAxis: 100 }],
                    ],
                },
            }],
            yAxis: { min: 0, max: 100 },
        });

        // Pressure
        charts.pressure = echarts.init(elements.pressure);
        charts.pressure.setOption(makeOption('hPa', [
            { name: 'Pressure', color: '#9b5de5', area: 'rgba(155,93,229,0.08)' },
        ]));

        // Vibration
        charts.vibration = echarts.init(elements.vibration);
        charts.vibration.setOption(makeOption('m/s\u00B2', [
            { name: 'Avg', color: '#00b4d8' },
            { name: 'Peak', color: '#ef476f' },
        ]));
    }

    function _ts2data(timestamps, values) {
        var d = [];
        for (var i = 0; i < timestamps.length; i++) {
            d.push([timestamps[i] * 1000, values[i]]);
        }
        return d;
    }

    function updatePower(data) {
        if (!charts.battVolt || !data.timestamps || !data.timestamps.length) return;
        charts.battVolt.setOption({ series: [{ data: _ts2data(data.timestamps, data.ch0_voltage) }] });
        charts.battCurr.setOption({ series: [{ data: _ts2data(data.timestamps, data.ch0_current) }] });
        charts.loadVolt.setOption({ series: [{ data: _ts2data(data.timestamps, data.ch1_voltage) }] });
        charts.loadCurr.setOption({ series: [{ data: _ts2data(data.timestamps, data.ch1_current) }] });
    }

    function updateEnv(data) {
        if (!charts.temp || !data.timestamps || !data.timestamps.length) return;
        charts.temp.setOption({ series: [{ data: _ts2data(data.timestamps, data.temperature) }] });
        charts.humidity.setOption({ series: [{ data: _ts2data(data.timestamps, data.humidity) }] });
        charts.pressure.setOption({ series: [{ data: _ts2data(data.timestamps, data.pressure) }] });
    }

    function updateAccel(data) {
        if (!charts.vibration || !data.timestamps || !data.timestamps.length) return;
        charts.vibration.setOption({
            series: [
                { data: _ts2data(data.timestamps, data.vib_avg) },
                { data: _ts2data(data.timestamps, data.vib_peak) },
            ],
        });
    }

    function resize() {
        Object.keys(charts).forEach(function (k) {
            if (charts[k]) charts[k].resize();
        });
    }

    return {
        init: init,
        updatePower: updatePower,
        updateEnv: updateEnv,
        updateAccel: updateAccel,
        resize: resize,
    };
})();
