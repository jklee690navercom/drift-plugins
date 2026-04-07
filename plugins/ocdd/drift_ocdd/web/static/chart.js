/* OCDD 플러그인 전문가 차트 — v2.0 (IQR 기반 outlier ratio) */

let ocddRatioChart = null;

function loadExpertFromCache() {
    fetch('/drift/ocdd/api/chart-data')
        .then(r => r.json())
        .then(data => {
            const rows = data.data || [];
            if (rows.length === 0) return;
            const events = data.drift_events || [];
            const lastEv = events.length > 0 ? events[events.length - 1] : null;
            const detail = (lastEv && lastEv.detail) || {};
            renderExpertCharts(rows, detail);
            renderResults(events);
        })
        .catch(err => console.error('Expert load error:', err));
}

function runExample() {
    const params = getParams();
    fetch('/drift/ocdd/api/example', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({params: params}),
    })
    .then(r => r.json())
    .then(resp => {
        if (resp.events && resp.events.length > 0) {
            const detail = resp.events[resp.events.length - 1].detail || {};
            renderExpertCharts(resp.data, detail);
        }
        renderResults(resp.events || []);
    })
    .catch(err => console.error('Error:', err));
}

function getParams() {
    return {
        window_size: parseInt(document.getElementById('param-window').value),
        rho: parseFloat(document.getElementById('param-rho').value),
        baseline_ratio: parseFloat(document.getElementById('param-baseline').value),
    };
}

function renderExpertCharts(data, detail) {
    const labels = (data || []).map(d => {
        const ts = new Date(d.timestamp);
        return ts.toLocaleString('ko-KR', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
    });

    const rows = data || [];
    const hasRowSeries = rows.length > 0 && rows[0].outlier_ratio !== undefined;
    const outlierRatioSeries = hasRowSeries ? rows.map(r => r.outlier_ratio)
                                            : (detail.outlier_ratio_series || []);
    const alarmMask = hasRowSeries ? rows.map(r => r.alarm || 0)
                                   : (detail.alarm_mask || []);
    const rho = hasRowSeries ? (rows[rows.length - 1].rho || 0.3)
                             : (detail.rho || 0.3);
    const baselineEnd = detail.baseline_end || 0;

    const ctx = document.getElementById('ocdd-ratio-chart');
    if (!ctx) return;
    if (ocddRatioChart) ocddRatioChart.destroy();

    const datasets = [
        {
            label: 'Outlier Ratio (\u03b1)',
            data: outlierRatioSeries,
            borderColor: '#3b82f6',
            borderWidth: 2,
            pointRadius: 0,
            fill: false,
            order: 2,
        },
        {
            label: '\u03c1 Threshold (' + rho.toFixed(2) + ')',
            data: Array(labels.length).fill(rho),
            borderColor: '#ef4444',
            borderDash: [6, 3],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
            order: 3,
        },
    ];

    // Alarm points on ratio line
    if (alarmMask.length > 0) {
        const alarmVals = outlierRatioSeries.map((v, i) => alarmMask[i] ? v : null);
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

    ocddRatioChart = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: { labels: labels, datasets: datasets },
        options: {
            responsive: true,
            scales: {
                x: { display: true, ticks: { maxTicksLimit: 10 } },
                y: {
                    display: true,
                    beginAtZero: true,
                    max: 1.0,
                    title: { display: true, text: 'Outlier Ratio' }
                }
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

    // Peak alpha
    const peakAlphas = events.map(e => (e.detail || {}).peak_alpha || 0);
    const maxAlpha = Math.max(...peakAlphas);
    if (el('stat-peak-alpha')) el('stat-peak-alpha').textContent = maxAlpha.toFixed(3);

    // IQR bounds
    if (events.length > 0 && events[0].detail) {
        const d = events[0].detail;
        const lb = (d.lower_bound !== undefined) ? d.lower_bound.toFixed(4) : '-';
        const ub = (d.upper_bound !== undefined) ? d.upper_bound.toFixed(4) : '-';
        if (el('stat-iqr')) el('stat-iqr').textContent = lb + ' ~ ' + ub;
    }

    const tbody = document.querySelector('#events-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    for (const e of events) {
        const d = e.detail || {};
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${e.detected_at || '-'}</td>
            <td>${(d.peak_alpha !== undefined) ? d.peak_alpha.toFixed(3) : '-'}</td>
            <td>${e.score.toFixed(2)}</td>
            <td><span class="severity-${e.severity}">${e.severity}</span></td>
            <td>${e.message || '-'}</td>
        `;
        tbody.appendChild(tr);
    }
}
