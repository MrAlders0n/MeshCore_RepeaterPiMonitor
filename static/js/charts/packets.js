var PacketsChart = (function () {
    var chart = null;

    var TT = { trigger: 'axis', backgroundColor: 'rgba(30,30,50,0.95)', borderColor: '#555', textStyle: { color: '#e0e0e0' } };
    var AX = { axisLine: { lineStyle: { color: '#888' } }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } } };

    var SERIES = [
        { name: 'RX Direct',    color: '#06d6a0', stack: 'packets' },
        { name: 'RX Flood',     color: '#90e0c0', stack: 'packets' },
        { name: 'TX Direct',    color: '#00b4d8', stack: 'packets' },
        { name: 'TX Flood',     color: '#80d8ee', stack: 'packets' },
        { name: 'RX Errors',    color: '#ef476f', stack: 'packets' },
    ];

    function init(el) {
        chart = echarts.init(el);
        chart.setOption({
            backgroundColor: 'transparent',
            tooltip: TT,
            legend: {
                data: SERIES.map(function (s) { return s.name; }),
                textStyle: { fontSize: 11, color: '#aaa' },
                top: 0,
            },
            xAxis: { type: 'time', axisLine: AX.axisLine },
            yAxis: { type: 'value', name: 'Count', nameTextStyle: { color: '#888' }, axisLine: AX.axisLine, splitLine: AX.splitLine },
            dataZoom: [
                { type: 'inside', xAxisIndex: 0 },
                { type: 'slider', xAxisIndex: 0, height: 20, bottom: 5 },
            ],
            series: SERIES.map(function (s) {
                return {
                    name: s.name,
                    type: 'bar',
                    stack: s.stack,
                    itemStyle: { color: s.color },
                    data: [],
                };
            }),
            grid: { left: 50, right: 16, top: 30, bottom: 50 },
        });
        return chart;
    }

    function update(data) {
        if (!chart) return;
        var keys = ['rx_direct', 'rx_flood', 'tx_direct', 'tx_flood', 'rx_errors'];
        var seriesData = keys.map(function () { return []; });
        for (var i = 0; i < data.timestamps.length; i++) {
            var t = data.timestamps[i] * 1000;
            for (var k = 0; k < keys.length; k++) {
                seriesData[k].push([t, data[keys[k]][i]]);
            }
        }
        chart.setOption({
            series: seriesData.map(function (d) { return { data: d }; }),
        });
    }

    return { init: init, update: update, resize: function () { if (chart) chart.resize(); } };
})();

var AirtimeChart = (function () {
    var chart = null;

    var TT = { trigger: 'axis', backgroundColor: 'rgba(30,30,50,0.95)', borderColor: '#555', textStyle: { color: '#e0e0e0' }, valueFormatter: function (v) { return v + '%'; } };
    var AX = { axisLine: { lineStyle: { color: '#888' } }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } } };

    function init(el) {
        chart = echarts.init(el);
        chart.setOption({
            backgroundColor: 'transparent',
            tooltip: TT,
            legend: {
                data: ['TX %', 'RX %'],
                textStyle: { fontSize: 11, color: '#aaa' },
                top: 0,
            },
            xAxis: { type: 'time', axisLine: AX.axisLine },
            yAxis: { type: 'value', name: '%', nameTextStyle: { color: '#888' }, axisLine: AX.axisLine, splitLine: AX.splitLine },
            dataZoom: [
                { type: 'inside', xAxisIndex: 0 },
                { type: 'slider', xAxisIndex: 0, height: 20, bottom: 5 },
            ],
            series: [
                {
                    name: 'TX %',
                    type: 'line',
                    smooth: true,
                    symbol: 'none',
                    areaStyle: { opacity: 0.3 },
                    lineStyle: { width: 2, color: '#00b4d8' },
                    itemStyle: { color: '#00b4d8' },
                    data: [],
                },
                {
                    name: 'RX %',
                    type: 'line',
                    smooth: true,
                    symbol: 'none',
                    areaStyle: { opacity: 0.3 },
                    lineStyle: { width: 2, color: '#06d6a0' },
                    itemStyle: { color: '#06d6a0' },
                    data: [],
                },
            ],
            grid: { left: 50, right: 16, top: 30, bottom: 50 },
        });
        return chart;
    }

    function update(data) {
        if (!chart) return;
        var tx = [], rx = [];
        for (var i = 0; i < data.timestamps.length; i++) {
            var t = data.timestamps[i] * 1000;
            tx.push([t, data.tx_pct[i]]);
            rx.push([t, data.rx_pct[i]]);
        }
        chart.setOption({
            series: [{ data: tx }, { data: rx }],
        });
    }

    return { init: init, update: update, resize: function () { if (chart) chart.resize(); } };
})();
