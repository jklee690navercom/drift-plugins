/* Hotelling T2 플러그인 차트 */

let valueChart = null;
let t2Chart = null;

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
    fetch('/drift/hotelling/api/example')
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

    // alarm 정보 추출
    let alarmMask = [], t2Series = [], threshold = 6.63;
    if (events.length > 0 && events[0].detail) {
        alarmMask = events[0].detail.alarm_mask || [];
        t2Series = events[0].detail.t2_series || [];
        threshold = events[0].detail.threshold || 6.63;
    }

    // Value Chart (상단)
    const valueCtx = document.getElementById('main-chart').getContext('2d');
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
                pointRadius: 4,
                showLine: false,
            }]
        },
        options: {
            responsive: true,
            scales: { x: { ticks: { maxTicksLimit: 10 } } },
            plugins: { legend: { display: true } }
        }
    });

    // T² Chart (하단) — 있으면 표시
    const t2Canvas = document.getElementById('t2-chart');
    if (t2Canvas && t2Series.length > 0) {
        const t2Ctx = t2Canvas.getContext('2d');
        if (t2Chart) t2Chart.destroy();
        t2Chart = new Chart(t2Ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'T² statistic',
                    data: t2Series,
                    borderColor: '#8b5cf6',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    fill: false,
                }, {
                    label: `Threshold (${threshold.toFixed(2)})`,
                    data: Array(labels.length).fill(threshold),
                    borderColor: '#ef4444',
                    borderDash: [5, 5],
                    borderWidth: 1,
                    pointRadius: 0,
                    fill: false,
                }]
            },
            options: {
                responsive: true,
                scales: {
                    x: { ticks: { maxTicksLimit: 10 } },
                    y: { beginAtZero: true }
                },
                plugins: { legend: { display: true } }
            }
        });
    }
}

function renderResults(events) {
    const section = document.getElementById('results-section');
    if (events.length === 0) { section.style.display = 'none'; return; }
    section.style.display = 'block';
    document.getElementById('stat-alarms').textContent = events.length;
    document.getElementById('stat-score').textContent = Math.max(...events.map(e => e.score)).toFixed(2);
    document.getElementById('stat-severity').textContent = events.reduce((max, e) =>
        e.severity === 'critical' ? 'critical' : (max === 'critical' ? max : e.severity), 'normal');
    const tbody = document.querySelector('#events-table tbody');
    tbody.innerHTML = '';
    for (const e of events) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${e.detected_at}</td><td>${e.score.toFixed(2)}</td>
            <td><span class="severity-${e.severity}">${e.severity}</span></td><td>${e.message}</td>`;
        tbody.appendChild(tr);
    }
}
