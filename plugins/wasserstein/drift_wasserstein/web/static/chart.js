/* Wasserstein 플러그인 전문가 차트 — v2.0 */

let wassersteinChart = null;

function loadExpertFromCache() {
    fetch('/drift/wasserstein/api/chart-data')
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
    fetch('/drift/wasserstein/api/example', {
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
        threshold: parseFloat(document.getElementById('param-threshold').value),
        reference_ratio: parseFloat(document.getElementById('param-refratio').value),
        lambda_smooth: parseFloat(document.getElementById('param-lambda').value),
        baseline_ratio: parseFloat(document.getElementById('param-baseline').value),
        update_reference: document.getElementById('param-updateref').checked,
    };
}

function renderExpertCharts(data, detail) {
    const labels = (data || []).map(d => {
        const ts = new Date(d.timestamp);
        return ts.toLocaleString('ko-KR', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
    });

    const rows = data || [];
    const hasRowSeries = rows.length > 0 && rows[0].w_distance !== undefined;
    const distSeries = hasRowSeries ? rows.map(r => r.w_distance)
                                    : (detail.distance_series || []);
    const smoothedSeries = hasRowSeries ? rows.map(r => r.w_smoothed)
                                        : (detail.smoothed_series || []);
    const threshold = hasRowSeries ? (rows[rows.length - 1].threshold || 0.1)
                                   : (detail.threshold || 0.1);
    const alarmMask = hasRowSeries ? rows.map(r => r.alarm || 0)
                                   : (detail.alarm_mask || []);

    const ctx = document.getElementById('wasserstein-chart');
    if (!ctx) return;
    if (wassersteinChart) wassersteinChart.destroy();

    const datasets = [
        {
            label: 'Raw Distance',
            data: distSeries,
            borderColor: '#94a3b8',
            borderWidth: 1,
            pointRadius: 0,
            fill: false,
            order: 3,
        },
        {
            label: 'EWMA Smoothed',
            data: smoothedSeries,
            borderColor: '#3b82f6',
            borderWidth: 2.5,
            pointRadius: 0,
            fill: false,
            order: 2,
        },
        {
            label: 'Threshold (' + threshold.toFixed(4) + ')',
            data: Array(labels.length).fill(threshold),
            borderColor: '#ef4444',
            borderDash: [6, 3],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
            order: 4,
        },
    ];

    // Alarm points on smoothed line
    if (alarmMask.length > 0) {
        const alarmVals = smoothedSeries.map((v, i) => alarmMask[i] ? v : null);
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

    wassersteinChart = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: { labels: labels, datasets: datasets },
        options: {
            responsive: true,
            scales: {
                x: { display: true, ticks: { maxTicksLimit: 10 } },
                y: { display: true, beginAtZero: true, title: { display: true, text: 'Wasserstein Distance' } }
            },
            plugins: {
                legend: { display: true },
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

    // Severity
    const maxSeverity = events.reduce((max, e) =>
        e.severity === 'critical' ? 'critical' : (max === 'critical' ? max : e.severity), 'normal');
    if (el('stat-severity')) el('stat-severity').textContent = maxSeverity;

    // Reference info
    if (events.length > 0 && events[0].detail) {
        const d = events[0].detail;
        const mu = (d.ref_mean !== undefined) ? d.ref_mean.toFixed(3) : '-';
        const sig = (d.ref_std !== undefined) ? d.ref_std.toFixed(3) : '-';
        if (el('stat-ref')) el('stat-ref').textContent = mu + ' / ' + sig;
    }

    const tbody = document.querySelector('#events-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    for (const e of events) {
        const d = e.detail || {};
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${e.detected_at || '-'}</td>
            <td>${(d.peak_distance !== undefined) ? d.peak_distance.toFixed(4) : '-'}</td>
            <td>${(d.peak_smoothed !== undefined) ? d.peak_smoothed.toFixed(4) : '-'}</td>
            <td>${e.score.toFixed(2)}</td>
            <td><span class="severity-${e.severity}">${e.severity}</span></td>
        `;
        tbody.appendChild(tr);
    }
}
