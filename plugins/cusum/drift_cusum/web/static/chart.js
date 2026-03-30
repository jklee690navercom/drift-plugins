/* CUSUM 플러그인 전문가 차트 — v2.0 */

let cusumStatChart = null;
let zscoreChart = null;

function loadExpertFromCache() {
    fetch('/drift/cusum/api/chart-data')
        .then(r => r.json())
        .then(data => {
            if (data.drift_events && data.drift_events.length > 0) {
                const detail = data.drift_events[data.drift_events.length - 1].detail || {};
                renderExpertCharts(data.data, detail);
                renderResults(data.drift_events);
            }
        })
        .catch(err => console.error('Expert load error:', err));
}

function runExample() {
    const params = getParams();
    fetch('/drift/cusum/api/example', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({params: params}),
    })
    .then(r => r.json())
    .then(resp => {
        if (resp.events && resp.events.length > 0) {
            const detail = resp.events[resp.events.length - 1].detail || {};
            renderExpertCharts(resp.data, detail);
            renderResults(resp.events);
        }
    })
    .catch(err => console.error('Error:', err));
}

function getParams() {
    const firVal = document.getElementById('param-fir').value;
    return {
        k: parseFloat(document.getElementById('param-k').value),
        h: parseFloat(document.getElementById('param-h').value),
        baseline_ratio: parseFloat(document.getElementById('param-baseline').value),
        reset: document.getElementById('param-reset').checked,
        robust: document.getElementById('param-robust').checked,
        fir: firVal ? parseFloat(firVal) : null,
    };
}

function renderExpertCharts(data, detail) {
    const labels = (data || []).map(d => {
        const ts = new Date(d.timestamp);
        return ts.toLocaleString('ko-KR', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
    });

    const sPosData = detail.s_pos_series || [];
    const sNegData = detail.s_neg_series || [];
    const zScoreData = detail.z_series || [];
    const threshold = detail.threshold_h || 5.0;
    const alarmMask = detail.alarm_mask || [];
    const baselineEnd = detail.baseline_end || 0;

    // CUSUM S+/S- chart
    const ctx1 = document.getElementById('cusum-stat-chart');
    if (!ctx1) return;
    if (cusumStatChart) cusumStatChart.destroy();

    const datasets = [
        {
            label: 'S+ (상향)',
            data: sPosData,
            borderColor: '#22c55e',
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
        },
        {
            label: 'S- (하향)',
            data: sNegData,
            borderColor: '#ef4444',
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
        },
        {
            label: 'Threshold (h=' + threshold.toFixed(1) + ')',
            data: Array(labels.length).fill(threshold),
            borderColor: '#f59e0b',
            borderDash: [5, 5],
            borderWidth: 1,
            pointRadius: 0,
            fill: false,
        },
    ];

    // Alarm points
    if (alarmMask.length > 0) {
        const alarmVals = sPosData.map((sp, i) =>
            alarmMask[i] ? Math.max(sp, sNegData[i] || 0) : null);
        datasets.push({
            label: 'Alarm',
            data: alarmVals,
            borderColor: 'transparent',
            pointBackgroundColor: '#dc2626',
            pointRadius: 4,
            showLine: false,
        });
    }

    cusumStatChart = new Chart(ctx1.getContext('2d'), {
        type: 'line',
        data: { labels: labels, datasets: datasets },
        options: {
            responsive: true,
            scales: {
                x: { display: true, ticks: { maxTicksLimit: 10 } },
                y: { display: true, beginAtZero: true, title: { display: true, text: 'CUSUM Statistic' } }
            },
            plugins: {
                legend: { display: true },
                annotation: baselineEnd > 0 ? {
                    annotations: {
                        baselineLine: {
                            type: 'line',
                            xMin: baselineEnd,
                            xMax: baselineEnd,
                            borderColor: '#6366f1',
                            borderWidth: 2,
                            borderDash: [4, 4],
                            label: { display: true, content: 'Baseline End', position: 'start' }
                        }
                    }
                } : {}
            }
        }
    });

    // Z-score chart
    const ctx2 = document.getElementById('zscore-chart');
    if (!ctx2) return;
    if (zscoreChart) zscoreChart.destroy();

    zscoreChart = new Chart(ctx2.getContext('2d'), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'z-score',
                data: zScoreData,
                borderColor: '#6366f1',
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
            }, {
                label: '\u00b1k zone',
                data: Array(labels.length).fill(0),
                borderColor: '#94a3b8',
                borderDash: [3, 3],
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: { display: true, ticks: { maxTicksLimit: 10 } },
                y: { display: true, title: { display: true, text: 'Standardized Value' } }
            },
            plugins: { legend: { display: true } }
        }
    });
}

function renderResults(events) {
    const section = document.getElementById('results-section');
    if (!events || events.length === 0) {
        if (section) section.style.display = 'none';
        return;
    }
    if (section) section.style.display = 'block';

    const el = id => document.getElementById(id);
    if (el('stat-alarms')) el('stat-alarms').textContent = events.length;
    if (el('stat-score')) el('stat-score').textContent = Math.max(...events.map(e => e.score)).toFixed(2);

    // Direction
    const dirs = events.map(e => (e.detail || {}).alarm_direction || '-');
    const hasPos = dirs.includes('positive');
    const hasNeg = dirs.includes('negative');
    const dirText = hasPos && hasNeg ? 'Both' : hasPos ? 'Positive \u2191' : hasNeg ? 'Negative \u2193' : '-';
    if (el('stat-direction')) el('stat-direction').textContent = dirText;

    // Baseline info
    if (events.length > 0 && events[0].detail) {
        const d = events[0].detail;
        const mu = (d.mu0 !== undefined) ? d.mu0.toFixed(3) : '-';
        const sig = (d.sigma0 !== undefined) ? d.sigma0.toFixed(3) : '-';
        if (el('stat-baseline')) el('stat-baseline').textContent = mu + ' / ' + sig;
    }

    const tbody = document.querySelector('#events-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    for (const e of events) {
        const d = e.detail || {};
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${e.detected_at || '-'}</td>
            <td>${(d.s_pos !== undefined) ? d.s_pos.toFixed(2) : '-'}</td>
            <td>${(d.s_neg !== undefined) ? d.s_neg.toFixed(2) : '-'}</td>
            <td>${e.score.toFixed(2)}</td>
            <td><span class="severity-${e.severity}">${e.severity}</span></td>
            <td>${d.alarm_direction || '-'}</td>
        `;
        tbody.appendChild(tr);
    }
}
