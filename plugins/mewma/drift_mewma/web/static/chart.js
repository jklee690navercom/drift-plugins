/* MEWMA 플러그인 전문가 차트 — D² 및 Per-feature EWMA traces */

let d2Chart = null;
let ewmaTracesChart = null;

const FEATURE_COLORS = [
    '#3b82f6', '#ef4444', '#22c55e', '#f59e0b', '#8b5cf6',
    '#06b6d4', '#ec4899', '#14b8a6', '#f97316', '#6366f1',
];

function loadExpertFromCache() {
    fetch('/drift/mewma/api/chart-data')
        .then(r => r.json())
        .then(data => {
            const rows = data.data || [];
            if (rows.length === 0) return;
            const events = data.drift_events || [];
            const lastEv = events.length > 0 ? events[events.length - 1] : null;
            const detail = (lastEv && lastEv.detail) || {};
            renderD2Chart(rows, detail);
            renderEwmaTraces(rows, detail);
            renderMewmaResults(events);
        })
        .catch(err => console.error('Expert load error:', err));
}

function runMewmaExample() {
    const params = getMewmaParams();
    fetch('/drift/mewma/api/example', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({params: params}),
    })
    .then(r => r.json())
    .then(resp => {
        if (resp.events && resp.events.length > 0) {
            const detail = resp.events[resp.events.length - 1].detail || {};
            renderD2Chart(resp.data, detail);
            renderEwmaTraces(resp.data, detail);
        }
        renderMewmaResults(resp.events || []);
    })
    .catch(err => console.error('MEWMA Error:', err));
}

function getMewmaParams() {
    return {
        lambda_: parseFloat(document.getElementById('param-lambda').value),
        alpha: parseFloat(document.getElementById('param-alpha').value),
        baseline_ratio: parseFloat(document.getElementById('param-baseline').value),
    };
}

function renderD2Chart(data, detail) {
    const labels = (data || []).map(d => {
        const ts = new Date(d.timestamp);
        return ts.toLocaleString('ko-KR', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
    });

    const rows = data || [];
    const hasRowSeries = rows.length > 0 && rows[0].d2 !== undefined;
    const d2Series = hasRowSeries ? rows.map(r => r.d2)
                                  : (detail.d2_series || []);
    const alarmMask = hasRowSeries ? rows.map(r => r.alarm || 0)
                                   : (detail.alarm_mask || []);
    const ucl = hasRowSeries ? (rows[rows.length - 1].ucl || 0)
                             : (detail.ucl || 0);
    const baselineEnd = detail.baseline_end || 0;

    const ctx = document.getElementById('d2-chart');
    if (!ctx) return;
    if (d2Chart) d2Chart.destroy();

    const datasets = [
        {
            label: 'D² Statistic',
            data: d2Series,
            borderColor: '#3b82f6',
            borderWidth: 2,
            pointRadius: 0,
            fill: false,
            order: 2,
        },
        {
            label: 'UCL (' + ucl.toFixed(2) + ')',
            data: Array(labels.length).fill(ucl),
            borderColor: '#ef4444',
            borderDash: [6, 3],
            borderWidth: 2,
            pointRadius: 0,
            fill: false,
            order: 3,
        },
    ];

    // Alarm points
    if (alarmMask.length > 0) {
        const alarmVals = d2Series.map((v, i) => alarmMask[i] ? v : null);
        datasets.push({
            label: 'Alarm',
            data: alarmVals,
            borderColor: 'transparent',
            pointBackgroundColor: '#dc2626',
            pointRadius: 5,
            pointBorderWidth: 2,
            pointBorderColor: '#fff',
            showLine: false,
            order: 1,
        });
    }

    d2Chart = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: { labels: labels, datasets: datasets },
        options: {
            responsive: true,
            scales: {
                x: { display: true, ticks: { maxTicksLimit: 10 } },
                y: { display: true, title: { display: true, text: 'D² (Mahalanobis Distance)' } }
            },
            plugins: {
                legend: { display: true },
                annotation: baselineEnd > 0 ? {
                    annotations: {
                        baselineLine: {
                            type: 'line',
                            xMin: baselineEnd,
                            xMax: baselineEnd,
                            borderColor: '#8b5cf6',
                            borderWidth: 2,
                            borderDash: [4, 4],
                            label: { display: true, content: 'Baseline End', position: 'start' }
                        }
                    }
                } : {}
            }
        }
    });
}

function renderEwmaTraces(data, detail) {
    const labels = (data || []).map(d => {
        const ts = new Date(d.timestamp);
        return ts.toLocaleString('ko-KR', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
    });

    const rows = data || [];
    // cache row에서 ewma_<feature> 컬럼을 찾아 per-feature series 구성
    let ewmaSeries = {};
    let featureNames = [];
    if (rows.length > 0) {
        featureNames = Object.keys(rows[0])
            .filter(k => k.startsWith('ewma_'))
            .map(k => k.substring(5));
    }
    if (featureNames.length > 0) {
        featureNames.forEach(name => {
            ewmaSeries[name] = rows.map(r => r['ewma_' + name]);
        });
    } else {
        // fallback: detail.ewma_series
        ewmaSeries = detail.ewma_series || {};
        featureNames = detail.feature_names || Object.keys(ewmaSeries);
    }
    const mu0 = detail.mu0 || [];
    const baselineEnd = detail.baseline_end || 0;

    const ctx = document.getElementById('ewma-traces-chart');
    if (!ctx) return;
    if (ewmaTracesChart) ewmaTracesChart.destroy();

    const datasets = [];
    featureNames.forEach((name, idx) => {
        const color = FEATURE_COLORS[idx % FEATURE_COLORS.length];
        datasets.push({
            label: 'Z(' + name + ')',
            data: ewmaSeries[name] || [],
            borderColor: color,
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
        });
        // mu0 reference line
        if (mu0[idx] !== undefined) {
            datasets.push({
                label: 'μ0(' + name + ')=' + mu0[idx].toFixed(2),
                data: Array(labels.length).fill(mu0[idx]),
                borderColor: color,
                borderDash: [3, 3],
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
            });
        }
    });

    ewmaTracesChart = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: { labels: labels, datasets: datasets },
        options: {
            responsive: true,
            scales: {
                x: { display: true, ticks: { maxTicksLimit: 10 } },
                y: { display: true, title: { display: true, text: 'EWMA Z_t per Feature' } }
            },
            plugins: {
                legend: { display: true, labels: { font: { size: 10 } } },
                annotation: baselineEnd > 0 ? {
                    annotations: {
                        baselineLine: {
                            type: 'line',
                            xMin: baselineEnd,
                            xMax: baselineEnd,
                            borderColor: '#8b5cf6',
                            borderWidth: 2,
                            borderDash: [4, 4],
                            label: { display: true, content: 'Baseline End', position: 'start' }
                        }
                    }
                } : {}
            }
        }
    });
}

function renderMewmaResults(events) {
    const section = document.getElementById('results-section');
    if (!events || events.length === 0) {
        if (section) section.style.display = 'none';
        return;
    }
    if (section) section.style.display = 'block';

    const el = id => document.getElementById(id);
    if (el('stat-alarms')) el('stat-alarms').textContent = events.length;
    if (el('stat-score')) el('stat-score').textContent = Math.max(...events.map(e => e.score)).toFixed(2);

    if (events.length > 0 && events[0].detail) {
        const d = events[0].detail;
        if (el('stat-features')) el('stat-features').textContent = d.num_features || '-';
        if (el('stat-ucl')) el('stat-ucl').textContent = d.ucl !== undefined ? d.ucl.toFixed(2) : '-';
    }

    const tbody = document.querySelector('#events-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    for (const e of events) {
        const d = e.detail || {};
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${e.detected_at || '-'}</td>
            <td>${(d.d2_value !== undefined) ? d.d2_value.toFixed(4) : '-'}</td>
            <td>${e.score.toFixed(2)}</td>
            <td><span class="severity-${e.severity}">${e.severity}</span></td>
            <td>${d.alarm_count || '-'}</td>
        `;
        tbody.appendChild(tr);
    }
}
