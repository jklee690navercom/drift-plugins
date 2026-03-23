/* KS Test 플러그인 차트 */

let valueChart = null;
let ksStatChart = null;
let pvalueChart = null;

function togglePanel(id) {
    const panel = document.getElementById(id);
    const isVisible = panel.style.display !== 'none';
    document.querySelectorAll('.info-panel').forEach(p => p.style.display = 'none');
    document.querySelectorAll('.btn-info').forEach(b => b.classList.remove('active'));
    if (!isVisible) {
        panel.style.display = 'block';
        document.querySelectorAll('.btn-info').forEach(b => {
            if (b.getAttribute('onclick').includes(id)) b.classList.add('active');
        });
    }
}

function runExample() {
    fetch('/drift/ks_test/api/example')
        .then(r => r.json())
        .then(resp => {
            renderCharts(resp.data, resp.events);
            renderResults(resp.events);
        })
        .catch(err => console.error('Error:', err));
}

function renderCharts(data, events) {
    const labels = data.map(d => {
        const ts = new Date(d.timestamp);
        return ts.toLocaleString('ko-KR', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
    });
    const values = data.map(d => d.value);

    let alarmMask = [], ksSeries = [], pvalSeries = [];
    let alpha = 0.05;
    if (events.length > 0 && events[0].detail) {
        alarmMask = events[0].detail.alarm_mask || [];
        ksSeries = events[0].detail.ks_series || [];
        pvalSeries = events[0].detail.pvalue_series || [];
        alpha = events[0].detail.alpha || 0.05;
    }

    // Value Chart
    const valueCtx = document.getElementById('value-chart').getContext('2d');
    if (valueChart) valueChart.destroy();
    valueChart = new Chart(valueCtx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Value',
                data: values,
                borderColor: '#0f172a',
                borderWidth: 1.5,
                pointRadius: 0,
                fill: false,
            }, {
                label: 'Drift Detected',
                data: values.map((v, i) => alarmMask[i] ? v : null),
                borderColor: 'transparent',
                pointBackgroundColor: '#ef4444',
                pointRadius: 3,
                showLine: false,
            }]
        },
        options: {
            responsive: true,
            scales: { x: { ticks: { maxTicksLimit: 10 } } },
            plugins: { legend: { display: true } }
        }
    });

    // KS D-statistic Chart
    const ksCtx = document.getElementById('ks-stat-chart').getContext('2d');
    if (ksStatChart) ksStatChart.destroy();
    ksStatChart = new Chart(ksCtx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'D-statistic',
                data: ksSeries,
                borderColor: '#8b5cf6',
                borderWidth: 1.5,
                pointRadius: 0,
                fill: false,
            }]
        },
        options: {
            responsive: true,
            scales: { x: { ticks: { maxTicksLimit: 10 } }, y: { beginAtZero: true } },
            plugins: { legend: { display: true } }
        }
    });

    // p-value Chart (log scale)
    const pCtx = document.getElementById('pvalue-chart').getContext('2d');
    if (pvalueChart) pvalueChart.destroy();
    const pvalLog = pvalSeries.map(p => p > 0 ? -Math.log10(p) : 0);
    const alphaLine = -Math.log10(alpha);
    pvalueChart = new Chart(pCtx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '-log10(p-value)',
                data: pvalLog,
                borderColor: '#0ea5e9',
                borderWidth: 1.5,
                pointRadius: 0,
                fill: false,
            }, {
                label: `Threshold (alpha=${alpha})`,
                data: Array(labels.length).fill(alphaLine),
                borderColor: '#ef4444',
                borderDash: [5, 5],
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
            }]
        },
        options: {
            responsive: true,
            scales: { x: { ticks: { maxTicksLimit: 10 } }, y: { beginAtZero: true } },
            plugins: { legend: { display: true } }
        }
    });
}

function renderResults(events) {
    const section = document.getElementById('results-section');
    if (events.length === 0) {
        section.style.display = 'none';
        return;
    }
    section.style.display = 'block';

    document.getElementById('stat-alarms').textContent = events.length;
    document.getElementById('stat-dstat').textContent =
        Math.max(...events.map(e => e.detail.d_statistic || 0)).toFixed(4);
    document.getElementById('stat-pval').textContent =
        Math.min(...events.map(e => e.detail.p_value || 1)).toExponential(2);

    const tbody = document.querySelector('#events-table tbody');
    tbody.innerHTML = '';
    for (const e of events) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${e.detected_at}</td>
            <td>${(e.detail.d_statistic || 0).toFixed(4)}</td>
            <td>${(e.detail.p_value || 0).toExponential(2)}</td>
            <td><span class="severity-${e.severity}">${e.severity}</span></td>
            <td>${e.message}</td>
        `;
        tbody.appendChild(tr);
    }
}
