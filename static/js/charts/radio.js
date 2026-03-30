var RadioChart = (function () {
    var chart = null;
    var TT = { trigger: 'axis', backgroundColor: 'rgba(30,30,50,0.95)', borderColor: '#555', textStyle: { color: '#e0e0e0' } };
    var AX = { axisLine: { lineStyle: { color: '#888' } }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } } };
    function init(el) {
        chart = echarts.init(el);
        chart.setOption({
            backgroundColor: 'transparent',
            tooltip: TT,
            legend: {
                data: ['Noise Floor', 'Last RSSI', 'Last SNR'],
                textStyle: { fontSize: 11, color: '#aaa' },
                top: 0,
            },
            xAxis: { type: 'time', axisLine: AX.axisLine },
            yAxis: [
                { type: 'value', name: 'dBm', nameTextStyle: { color: '#888' }, axisLine: AX.axisLine, splitLine: AX.splitLine },
                { type: 'value', name: 'dB', nameTextStyle: { color: '#888' }, axisLine: AX.axisLine, splitLine: { show: false } },
            ],
            dataZoom: [
                { type: 'inside', xAxisIndex: 0 },
                { type: 'slider', xAxisIndex: 0, height: 20, bottom: 5 },
            ],
            series: [
                { name: 'Noise Floor', type: 'line', smooth: true, symbol: 'none', yAxisIndex: 0, lineStyle: { width: 2, color: '#ffd166' }, itemStyle: { color: '#ffd166' }, areaStyle: { opacity: 0.1, color: '#ffd166' }, data: [] },
                { name: 'Last RSSI', type: 'line', smooth: true, symbol: 'none', yAxisIndex: 0, lineStyle: { width: 2, color: '#ef476f' }, itemStyle: { color: '#ef476f' }, data: [] },
                { name: 'Last SNR', type: 'line', smooth: true, symbol: 'none', yAxisIndex: 1, lineStyle: { width: 2, color: '#06d6a0' }, itemStyle: { color: '#06d6a0' }, data: [] },
            ],
            grid: { left: 50, right: 50, top: 30, bottom: 50 },
        });
        return chart;
    }
    function update(data) {
        if (!chart) return;
        var nf = [], rssi = [], snr = [];
        for (var i = 0; i < data.timestamps.length; i++) {
            var t = data.timestamps[i] * 1000;
            nf.push([t, Math.round(data.noise_floor[i])]);
            rssi.push([t, data.last_rssi[i]]);
            snr.push([t, data.last_snr[i]]);
        }
        chart.setOption({ series: [{ data: nf }, { data: rssi }, { data: snr }] });
        // Compute 5-minute rolling average for noise floor
        var nfAvg = [];
        for (var i = 0; i < nf.length; i++) {
            var sum = 0, count = 0;
            for (var j = i; j >= 0 && nf[i][0] - nf[j][0] <= WINDOW; j--) {
                if (nf[j][1] != null) { sum += nf[j][1]; count++; }
            }
            nfAvg.push([nf[i][0], count > 0 ? Math.round(sum / count) : null]);
        }
        chart.setOption({ series: [{ data: nf }, { data: nfAvg }, { data: rssi }, { data: snr }] });
    }
    return { init: init, update: update, resize: function () { if (chart) chart.resize(); } };
})();
