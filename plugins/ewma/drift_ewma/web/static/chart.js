/* EWMA 플러그인 전문가 차트 — v2.0 */

let ewmaChart = null;

function loadExpertFromCache() {
    fetch('/drift/ewma/api/chart-data')
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
    fetch('/drift/ewma/api/example', {
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
        lambda_: parseFloat(document.getElementById('param-lambda').value),
        L: parseFloat(document.getElementById('param-L').value),
        baseline_ratio: parseFloat(document.getElementById('param-baseline').value),
        cooldown: parseInt(document.getElementById('param-cooldown').value),
        two_sided: document.getElementById('param-twosided').checked,
    };
}

function renderExpertCharts(data, detail) {
    const labels = (data || []).map(d => {
        const ts = new Date(d.timestamp);
        return ts.toLocaleString('ko-KR', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
    });

    const rows = data || [];
    const values = rows.map(d => d.value);
    // series는 cache row에서 직접 (detector가 row마다 적재); 없으면 detail fallback.
    const hasRowSeries = rows.length > 0 && rows[0].ewma !== undefined;
    const ewmaSeries = hasRowSeries ? rows.map(r => r.ewma)
                                    : (detail.ewma_series || []);
    const alarmMask = hasRowSeries ? rows.map(r => r.alarm || 0)
                                   : (detail.alarm_mask || []);
    const ucl = hasRowSeries ? (rows[rows.length - 1].ucl || 0)
                             : (detail.ucl || 0);
    const lcl = hasRowSeries ? (rows[rows.length - 1].lcl || 0)
                             : (detail.lcl || 0);
    const mu0 = hasRowSeries ? (rows[rows.length - 1].mu0 || 0)
                             : (detail.mu0 || 0);
    const baselineEnd = detail.baseline_end || 0;

    const ctx = document.getElementById('ewma-chart');
    if (!ctx) return;
    if (ewmaChart) ewmaChart.destroy();

    const datasets = [
        {
            label: 'Value',
            data: values,
            borderColor: '#94a3b8',
            borderWidth: 1,
            pointRadius: 0,
            fill: false,
            order: 5,
        },
        {
            label: 'EWMA',
            data: ewmaSeries,
            borderColor: '#3b82f6',
            borderWidth: 2.5,
            pointRadius: 0,
            fill: false,
            order: 2,
        },
        {
            label: 'UCL (' + ucl.toFixed(4) + ')',
            data: Array(labels.length).fill(ucl),
            borderColor: '#ef4444',
            borderDash: [6, 3],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
            order: 3,
        },
        {
            label: 'LCL (' + lcl.toFixed(4) + ')',
            data: Array(labels.length).fill(lcl),
            borderColor: '#ef4444',
            borderDash: [6, 3],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
            order: 3,
        },
        {
            label: 'μ0 (' + mu0.toFixed(4) + ')',
            data: Array(labels.length).fill(mu0),
            borderColor: '#22c55e',
            borderDash: [4, 4],
            borderWidth: 1,
            pointRadius: 0,
            fill: false,
            order: 4,
        },
    ];

    // Alarm points on EWMA line
    if (alarmMask.length > 0) {
        const alarmVals = ewmaSeries.map((z, i) => alarmMask[i] ? z : null);
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

    ewmaChart = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: { labels: labels, datasets: datasets },
        options: {
            responsive: true,
            scales: {
                x: { display: true, ticks: { maxTicksLimit: 10 } },
                y: { display: true, title: { display: true, text: 'EWMA Value' } }
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

    // Direction
    const dirs = events.map(e => (e.detail || {}).direction || '-');
    const hasUpper = dirs.includes('upper');
    const hasLower = dirs.includes('lower');
    const dirText = hasUpper && hasLower ? 'Both' : hasUpper ? 'Upper ↑' : hasLower ? 'Lower ↓' : '-';
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
            <td>${(d.ewma_value !== undefined) ? d.ewma_value.toFixed(4) : '-'}</td>
            <td>${e.score.toFixed(2)}</td>
            <td><span class="severity-${e.severity}">${e.severity}</span></td>
            <td>${d.direction || '-'}</td>
        `;
        tbody.appendChild(tr);
    }
}
