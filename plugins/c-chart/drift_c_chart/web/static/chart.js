/* C Chart 플러그인 차트 */

let cChart = null;

function togglePanel(id) {
    const panel = document.getElementById(id);
    const isVisible = panel.style.display !== 'none';
    document.querySelectorAll('.info-panel').forEach(p => p.style.display = 'none');
    document.querySelectorAll('.btn-info').forEach(b => b.classList.remove('active'));
    if (!isVisible) {
        panel.style.display = 'block';
        const buttons = document.querySelectorAll('.btn-info');
        buttons.forEach(b => {
            if (b.getAttribute('onclick').includes(id)) b.classList.add('active');
        });
    }
}

function runExample() {
    fetch('/drift/c_chart/api/example')
        .then(r => r.json())
        .then(resp => {
            renderCharts(resp.data, resp.events);
            renderResults(resp.events);
        })
        .catch(err => console.error('Error:', err));
}

function renderCharts(data, events) {
    const labels = data.map((d, i) => {
        const ts = new Date(d.timestamp);
        return ts.toLocaleString('ko-KR', {month:'2-digit', day:'2-digit', hour:'2-digit'});
    });
    const values = data.map(d => d.value);

    let alarmMask = [];
    let ucl = 0, lcl = 0, cl = 0;
    if (events.length > 0 && events[0].detail) {
        alarmMask = events[0].detail.alarm_mask || [];
        ucl = events[0].detail.ucl;
        lcl = events[0].detail.lcl;
        cl = events[0].detail.cl;
    }

    // Bar colors: red for alarm, blue for normal
    const barColors = values.map((v, i) => alarmMask[i] ? '#ef4444' : '#6366f1');

    // C Chart (bar chart with line overlays)
    const ctx = document.getElementById('c-chart').getContext('2d');
    if (cChart) cChart.destroy();
    cChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Count (c)',
                data: values,
                backgroundColor: barColors,
                borderColor: barColors,
                borderWidth: 1,
                order: 2,
            }, {
                label: 'UCL',
                data: Array(labels.length).fill(ucl),
                type: 'line',
                borderColor: '#ef4444',
                borderDash: [5, 5],
                borderWidth: 2,
                pointRadius: 0,
                fill: false,
                order: 1,
            }, {
                label: 'CL (c-bar)',
                data: Array(labels.length).fill(cl),
                type: 'line',
                borderColor: '#22c55e',
                borderDash: [3, 3],
                borderWidth: 2,
                pointRadius: 0,
                fill: false,
                order: 1,
            }, {
                label: 'LCL',
                data: Array(labels.length).fill(lcl),
                type: 'line',
                borderColor: '#ef4444',
                borderDash: [5, 5],
                borderWidth: 2,
                pointRadius: 0,
                fill: false,
                order: 1,
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: { display: true, ticks: { maxTicksLimit: 15 } },
                y: { display: true, beginAtZero: true }
            },
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
    document.getElementById('stat-score').textContent = Math.max(...events.map(e => e.score)).toFixed(2);
    document.getElementById('stat-severity').textContent = events.reduce((max, e) =>
        e.severity === 'critical' ? 'critical' : (max === 'critical' ? max : e.severity), 'normal');

    const tbody = document.querySelector('#events-table tbody');
    tbody.innerHTML = '';
    for (const e of events) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${e.detected_at}</td>
            <td>${e.score.toFixed(2)}</td>
            <td><span class="severity-${e.severity}">${e.severity}</span></td>
            <td>${e.message}</td>
        `;
        tbody.appendChild(tr);
    }
}
