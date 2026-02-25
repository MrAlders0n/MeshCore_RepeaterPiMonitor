var PowerCharts = (function () {
    var voltageChart = null;
    var currentChart = null;
    var powerChart = null;

    var CH_COLORS = ['#ffd166', '#00b4d8'];
    var CH_NAMES = ['Solar', 'Repeater'];

    // Channel mapping: which DB channel (ch0/ch1/ch2) maps to Solar and Repeater
    var solarCh = 'ch1';
    var repeaterCh = 'ch0';

    var TT = { trigger: 'axis', backgroundColor: 'rgba(30,30,50,0.95)', borderColor: '#555', textStyle: { color: '#e0e0e0' } };
    var AX = { axisLine: { lineStyle: { color: '#888' } }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } } };

    function makeOption(yName) {
        return {
            backgroundColor: 'transparent',
            tooltip: TT,
            legend: {
                data: CH_NAMES,
                textStyle: { fontSize: 11, color: '#aaa' },
                top: 0,
            },
            xAxis: { type: 'time', axisLine: AX.axisLine },
            yAxis: { type: 'value', name: yName, nameTextStyle: { color: '#888' }, axisLine: AX.axisLine, splitLine: AX.splitLine },
            dataZoom: [
                { type: 'inside', xAxisIndex: 0 },
                { type: 'slider', xAxisIndex: 0, height: 20, bottom: 5 },
            ],
            series: CH_NAMES.map(function (name, i) {
                return {
                    name: name,
                    type: 'line',
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 2, color: CH_COLORS[i] },
                    itemStyle: { color: CH_COLORS[i] },
                    data: [],
                };
            }),
            grid: { left: 50, right: 16, top: 30, bottom: 50 },
        };
    }

    function init(voltageEl, currentEl, powerEl) {
        voltageChart = echarts.init(voltageEl);
        currentChart = echarts.init(currentEl);
        powerChart = echarts.init(powerEl);
        voltageChart.setOption(makeOption('V'));
        currentChart.setOption(makeOption('mA'));
        powerChart.setOption(makeOption('mW'));
    }

    function setChannelMapping(solar, repeater) {
        solarCh = solar;
        repeaterCh = repeater;
    }

    function update(data) {
        if (!voltageChart) return;
        if (!data.timestamps.length) return;

        var voltageSeries = [[], []];
        var currentSeries = [[], []];
        var powerSeries = [[], []];

        for (var i = 0; i < data.timestamps.length; i++) {
            var t = data.timestamps[i] * 1000;
            voltageSeries[0].push([t, data[solarCh + '_voltage'][i]]);
            voltageSeries[1].push([t, data[repeaterCh + '_voltage'][i]]);
            currentSeries[0].push([t, data[solarCh + '_current'][i]]);
            currentSeries[1].push([t, data[repeaterCh + '_current'][i]]);
            powerSeries[0].push([t, data[solarCh + '_power'][i]]);
            powerSeries[1].push([t, data[repeaterCh + '_power'][i]]);
        }

        voltageChart.setOption({
            series: voltageSeries.map(function (d) { return { data: d }; }),
        });
        currentChart.setOption({
            series: currentSeries.map(function (d) { return { data: d }; }),
        });
        powerChart.setOption({
            series: powerSeries.map(function (d) { return { data: d }; }),
        });
    }

    function resize() {
        if (voltageChart) voltageChart.resize();
        if (currentChart) currentChart.resize();
        if (powerChart) powerChart.resize();
    }

    return { init: init, update: update, resize: resize, setChannelMapping: setChannelMapping };
})();


var BatteryChart = (function () {
    var chart = null;

    var TT = { trigger: 'axis', backgroundColor: 'rgba(30,30,50,0.95)', borderColor: '#555', textStyle: { color: '#e0e0e0' } };
    var AX = { axisLine: { lineStyle: { color: '#888' } }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } } };

    function init(el) {
        if (!el) return;
        chart = echarts.init(el);
        chart.setOption({
            backgroundColor: 'transparent',
            tooltip: TT,
            xAxis: { type: 'time', axisLine: AX.axisLine },
            yAxis: { type: 'value', name: 'mV', nameTextStyle: { color: '#888' }, axisLine: AX.axisLine, splitLine: AX.splitLine },
            dataZoom: [
                { type: 'inside', xAxisIndex: 0 },
                { type: 'slider', xAxisIndex: 0, height: 20, bottom: 5 },
            ],
            series: [{
                name: 'Battery',
                type: 'line',
                smooth: true,
                symbol: 'none',
                lineStyle: { width: 2, color: '#06d6a0' },
                itemStyle: { color: '#06d6a0' },
                areaStyle: { color: 'rgba(6, 214, 160, 0.1)' },
                data: [],
            }],
            grid: { left: 50, right: 16, top: 30, bottom: 50 },
        });
    }

    function update(data) {
        if (!chart) return;
        if (!data.timestamps || !data.timestamps.length) return;

        var seriesData = [];
        for (var i = 0; i < data.timestamps.length; i++) {
            seriesData.push([data.timestamps[i] * 1000, data.battery_mv[i]]);
        }

        chart.setOption({
            series: [{ data: seriesData }],
        });
    }

    function resize() {
        if (chart) chart.resize();
    }

    return { init: init, update: update, resize: resize };
})();
