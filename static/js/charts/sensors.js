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
            { name: 'Avg mA', color: '#ffd166' },
        ]));

        // Charge Voltage (Ch2)
        charts.solarVolt = echarts.init(elements.solarVolt);
        charts.solarVolt.setOption(makeOption('V', [
            { name: 'Charge V', color: '#f4a261', area: 'rgba(244,162,97,0.1)' },
        ]));

        // Charge Current (Ch2)
        charts.solarCurr = echarts.init(elements.solarCurr);
        charts.solarCurr.setOption(makeOption('mA', [
            { name: 'Charge mA', color: '#e76f51' },
        ]));

        // Power (W)
        if (elements.power) {
            charts.power = echarts.init(elements.power);
            charts.power.setOption(makeOption('W', [
                { name: 'Battery W', color: '#06d6a0' },
                { name: 'Load W', color: '#ef476f' },
                { name: 'Charge W', color: '#f4a261' },
            ]));
        }

        // Charger Status (BQ24074)
        if (elements.chargerStatus) {
            charts.chargerStatus = echarts.init(elements.chargerStatus);
            charts.chargerStatus.setOption({
                backgroundColor: 'transparent',
                tooltip: TT,
                legend: {
                    data: ['Charging', 'Power Good'],
                    textStyle: { fontSize: 11, color: '#aaa' },
                    top: 0,
                },
                xAxis: { type: 'time', axisLine: AX.axisLine },
                yAxis: {
                    type: 'value', name: 'State',
                    nameTextStyle: { color: '#888' },
                    min: -0.1, max: 1.1,
                    axisLine: AX.axisLine, splitLine: AX.splitLine,
                    axisLabel: {
                        formatter: function (v) { return v === 0 ? 'OFF' : v === 1 ? 'ON' : ''; },
                    },
                },
                dataZoom: [
                    { type: 'inside', xAxisIndex: 0 },
                    { type: 'slider', xAxisIndex: 0, height: 20, bottom: 5 },
                ],
                series: [
                    {
                        name: 'Charging', type: 'line', step: 'end', symbol: 'none',
                        lineStyle: { width: 2, color: '#06d6a0' },
                        itemStyle: { color: '#06d6a0' },
                        areaStyle: { color: 'rgba(6,214,160,0.1)' },
                        data: [],
                    },
                    {
                        name: 'Power Good', type: 'line', step: 'end', symbol: 'none',
                        lineStyle: { width: 2, color: '#ffd166' },
                        itemStyle: { color: '#ffd166' },
                        data: [],
                    },
                ],
                grid: { left: 50, right: 16, top: 30, bottom: 50 },
            });
        }

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

    function _mwToW(values) {
        return values.map(function (v) { return v != null ? Math.round(v / 10) / 100 : null; });
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
        var loadCurrData = _ts2data(data.timestamps, data.ch1_current);
        var loadCurrSum = 0, loadCurrCnt = 0;
        for (var i = 0; i < data.ch1_current.length; i++) {
            if (data.ch1_current[i] != null) { loadCurrSum += data.ch1_current[i]; loadCurrCnt++; }
        }
        var loadCurrAvg = loadCurrCnt ? Math.round(loadCurrSum / loadCurrCnt * 100) / 100 : 0;
        var avgLine = data.timestamps.map(function (t) { return [t * 1000, loadCurrAvg]; });
        charts.loadCurr.setOption({ series: [
            { data: loadCurrData },
            { data: avgLine, lineStyle: { type: 'dashed', width: 1.5 } },
        ] });
        if (charts.solarVolt && data.ch2_voltage) {
            charts.solarVolt.setOption({ series: [{ data: _ts2data(data.timestamps, data.ch2_voltage) }] });
        }
        if (charts.solarCurr && data.ch2_current) {
            charts.solarCurr.setOption({ series: [{ data: _ts2data(data.timestamps, data.ch2_current) }] });
        }
        if (charts.power && data.ch0_power) {
            charts.power.setOption({
                series: [
                    { data: _ts2data(data.timestamps, _mwToW(data.ch0_power)) },
                    { data: _ts2data(data.timestamps, _mwToW(data.ch1_power)) },
                    { data: _ts2data(data.timestamps, _mwToW(data.ch2_power)) },
                ],
            });
        }
    }

    function updateBq24074(data) {
        if (!charts.chargerStatus || !data.timestamps || !data.timestamps.length) return;
        charts.chargerStatus.setOption({
            series: [
                { data: _ts2data(data.timestamps, data.charging) },
                { data: _ts2data(data.timestamps, data.pgood) },
            ],
        });
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
        updateBq24074: updateBq24074,
        updateEnv: updateEnv,
        updateAccel: updateAccel,
        resize: resize,
    };
})();
