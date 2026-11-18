// assets/charts.js
mermaid.initialize({ startOnLoad: true, theme: 'neutral', securityLevel: 'loose' });

(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // --- Chart 1: mood space scatter (arousal x valence) ---
  var mood = echarts.init(document.getElementById('chart-mood-space'), null, { renderer: 'svg' });
  mood.setOption({
    animation: false,
    grid: { left: 64, right: 40, top: 36, bottom: 56 },
    tooltip: {
      appendToBody: true,
      formatter: function (p) {
        return '<b>' + p.name + '</b><br/>效价 ' + p.value[0] + ' · 唤醒度 ' + p.value[1];
      }
    },
    xAxis: {
      type: 'value', min: -1, max: 1,
      name: '效价 valence（负面 → 正面）',
      nameLocation: 'middle', nameGap: 32,
      nameTextStyle: { color: muted, fontSize: 12 },
      axisLabel: { color: muted }, axisLine: { lineStyle: { color: rule } },
      splitLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      type: 'value', min: -1, max: 1,
      name: '唤醒度 arousal（低 → 高）',
      nameTextStyle: { color: muted, fontSize: 12 },
      axisLabel: { color: muted }, axisLine: { lineStyle: { color: rule } },
      splitLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'scatter',
      symbolSize: 15,
      itemStyle: { color: accent, borderColor: ink, borderWidth: 1 },
      label: {
        show: true, position: 'right', distance: 8,
        formatter: '{b}', color: ink, fontSize: 12
      },
      markLine: {
        silent: true, symbol: 'none',
        lineStyle: { color: muted, type: 'dashed', width: 1 },
        label: { show: false },
        data: [{ xAxis: 0 }, { yAxis: 0 }]
      },
      data: [
        { name: '热情 / 燃', value: [0.60, 0.85] },
        { name: '欢快', value: [0.78, 0.42] },
        { name: '律动 groove', value: [0.42, 0.18] },
        { name: '舒缓 / 梦幻', value: [0.35, -0.60] },
        { name: '空灵 / 氛围', value: [0.08, -0.86] },
        { name: 'emo / 低沉', value: [-0.62, -0.52] },
        { name: '紧张 / 暗黑', value: [-0.48, 0.72] }
      ]
    }]
  });
  window.addEventListener('resize', function () { mood.resize(); });

  // --- Chart 2: maturity vs self-work scatter ---
  var mat = echarts.init(document.getElementById('chart-maturity'), null, { renderer: 'svg' });
  mat.setOption({
    animation: false,
    grid: { left: 64, right: 40, top: 48, bottom: 56 },
    tooltip: {
      appendToBody: true,
      formatter: function (p) {
        return '<b>' + p.name + '</b><br/>现成工具成熟度 ' + p.value[0] + ' / 5<br/>需自研工作量 ' + p.value[1] + ' / 5';
      }
    },
    legend: {
      top: 8, left: 'center',
      textStyle: { color: muted, fontSize: 12 },
      itemWidth: 14, itemHeight: 10
    },
    xAxis: {
      type: 'value', min: 1, max: 5.5,
      name: '现成工具成熟度（低 → 高）',
      nameLocation: 'middle', nameGap: 32,
      nameTextStyle: { color: muted, fontSize: 12 },
      axisLabel: { color: muted }, axisLine: { lineStyle: { color: rule } },
      splitLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      type: 'value', min: 1, max: 5.5,
      name: '需自研工作量（小 → 大）',
      nameTextStyle: { color: muted, fontSize: 12 },
      axisLabel: { color: muted }, axisLine: { lineStyle: { color: rule } },
      splitLine: { lineStyle: { color: rule } }
    },
    series: [
      {
        name: '本期模块',
        type: 'scatter',
        symbolSize: 15,
        itemStyle: { color: accent, borderColor: ink, borderWidth: 1 },
        label: { show: true, position: 'right', distance: 8, formatter: '{b}', color: ink, fontSize: 12 },
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: muted, type: 'dashed', width: 1 },
          label: { show: false },
          data: [{ xAxis: 3 }, { yAxis: 3 }]
        },
        data: [
          { name: '属性与曲风打标', value: [5.0, 1.5] },
          { name: '听感零样本标签', value: [3.5, 2.0] },
          { name: '切点与结构分析', value: [4.5, 2.0] },
          { name: '个性化分类器', value: [3.0, 3.2] },
          { name: '规则排歌器', value: [4.0, 2.5] }
        ]
      },
      {
        name: '远期 · 学习层',
        type: 'scatter',
        symbolSize: 15,
        itemStyle: { color: accent2, borderColor: ink, borderWidth: 1 },
        label: { show: true, position: 'right', distance: 8, formatter: '{b}', color: ink, fontSize: 12 },
        data: [
          { name: '过渡质量学习层', value: [1.5, 4.5] }
        ]
      }
    ]
  });
  window.addEventListener('resize', function () { mat.resize(); });
})();
