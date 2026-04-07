/* CUSUM 플러그인 전문가 차트 — v2.1 */

let cusumStatChart = null;
let zscoreChart = null;

function loadExpertFromCache() {
    fetch('/drift/cusum/api/chart-data')
        .then(r => r.json())
        .then(data => {
            const rows = data.data || [];
            const events = data.drift_events || [];
            // event가 없어도 cache row에 series가 있으면 차트를 그린다.
            if (rows.length === 0) return;
            // baseline_end / h_source 같은 메타는 마지막 event에서만 가져온다.
            const lastEv = events.length > 0 ? events[events.length - 1] : null;
            const detail = (lastEv && lastEv.detail) || {};
            renderExpertCharts(rows, detail);
            renderResults(events);
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
            // Show calibrated h in the input when auto mode
            if (resp.calibrated_h != null) {
                const hInput = document.getElementById('param-h');
                if (hInput) hInput.value = resp.calibrated_h.toFixed(2);
            }
        }
    })
    .catch(err => console.error('Error:', err));
}

function getParams() {
    const firVal = document.getElementById('param-fir').value;
    const autoH = document.getElementById('param-auto-h');
    const isAutoH = autoH && autoH.checked;
    const params = {
        k: parseFloat(document.getElementById('param-k').value),
        h: isAutoH ? 'auto' : parseFloat(document.getElementById('param-h').value),
        baseline_ratio: parseFloat(document.getElementById('param-baseline').value),
        reset: document.getElementById('param-reset').checked,
        robust: document.getElementById('param-robust').checked,
        fir: firVal ? parseFloat(firVal) : null,
    };
    if (isAutoH) {
        const calB = document.getElementById('param-cal-B');
        const calQ = document.getElementById('param-cal-q');
        if (calB) params.calibration_B = parseInt(calB.value) || 500;
        if (calQ) params.calibration_q = parseFloat(calQ.value) || 0.995;
    }
    return params;
}

function renderExpertCharts(data, detail) {
    const rows = data || [];
    const labels = rows.map(d => {
        const ts = new Date(d.timestamp);
        return ts.toLocaleString('ko-KR', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
    });

    // series는 cache row에서 직접 뽑는다 (detector가 row마다 적재).
    // 하위 호환: row에 없으면 detail의 series를 fallback으로 사용.
    const hasRowSeries = rows.length > 0 && rows[0].s_pos !== undefined;
    const sPosData = hasRowSeries ? rows.map(r => r.s_pos)
                                  : (detail.s_pos_series || []);
    const sNegData = hasRowSeries ? rows.map(r => r.s_neg)
                                  : (detail.s_neg_series || []);
    const zScoreData = hasRowSeries ? rows.map(r => (r.z !== undefined ? r.z : null))
                                    : (detail.z_series || []);
    const alarmMask = hasRowSeries ? rows.map(r => r.alarm || 0)
                                   : (detail.alarm_mask || []);
    // threshold는 row에 있으면 마지막 row 값(가장 최근 detect의 h)을 우선.
    const threshold = (hasRowSeries && rows[rows.length - 1].threshold_h !== undefined)
                    ? rows[rows.length - 1].threshold_h
                    : (detail.threshold_h || 5.0);
    const hSource = detail.h_source || 'manual';
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
            label: 'Threshold h=' + threshold.toFixed(2) + ' (' + hSource + ')',
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

        // h source info
        const hVal = (d.threshold_h !== undefined) ? d.threshold_h.toFixed(2) : '-';
        const hSrc = d.h_source || 'manual';
        if (el('stat-h-info')) el('stat-h-info').textContent = hVal + ' (' + hSrc + ')';
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
