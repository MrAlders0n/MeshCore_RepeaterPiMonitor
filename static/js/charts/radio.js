var RadioChart = (function () {
    var chart = null;

    function init(el, theme) {
        chart = echarts.init(el, theme);
        chart.setOption({
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(30, 30, 50, 0.95)',
                borderColor: '#555',
                textStyle: { color: '#e0e0e0' },
            },
            xAxis: { type: 'time' },
            yAxis: {
                type: 'value',
                name: 'dBm',
            },
            dataZoom: [
                { type: 'inside', xAxisIndex: 0 },
                { type: 'slider', xAxisIndex: 0, height: 20, bottom: 5 },
            ],
            series: [{
                name: 'Noise Floor',
                type: 'line',
                smooth: true,
                symbol: 'none',
                lineStyle: { width: 2, color: '#ffd166' },
                itemStyle: { color: '#ffd166' },
                areaStyle: { opacity: 0.1, color: '#ffd166' },
                data: [],
            }],
            grid: { left: 50, right: 16, top: 20, bottom: 50 },
        });
        return chart;
    }

    function update(data) {
        if (!chart) return;
        var series = [];
        for (var i = 0; i < data.timestamps.length; i++) {
            series.push([data.timestamps[i] * 1000, data.noise_floor[i]]);
        }
        chart.setOption({ series: [{ data: series }] });
    }

    return { init: init, update: update, resize: function () { if (chart) chart.resize(); } };
})();
