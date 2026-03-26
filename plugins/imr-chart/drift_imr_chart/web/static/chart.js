/* I-MR Chart 플러그인 차트 */

let iChart = null;
let mrChart = null;

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
    fetch('/drift/imr_chart/api/example')
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

    let alarmMask = [];
    let ucl = 0, lcl = 0, cl = 0, uclMr = 0, clMr = 0, mrValues = [];
    if (events.length > 0 && events[0].detail) {
        alarmMask = events[0].detail.alarm_mask || [];
        ucl = events[0].detail.ucl;
        lcl = events[0].detail.lcl;
        cl = events[0].detail.cl;
        uclMr = events[0].detail.ucl_mr;
        clMr = events[0].detail.cl_mr;
        mrValues = events[0].detail.mr_values || [];
    }

    // I Chart
    const iCtx = document.getElementById('i-chart').getContext('2d');
    if (iChart) iChart.destroy();
    iChart = new Chart(iCtx, {
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
                label: 'Alarm',
                data: values.map((v, i) => alarmMask[i] ? v : null),
                borderColor: 'transparent',
                pointBackgroundColor: '#ef4444',
                pointRadius: 4,
                showLine: false,
            }, {
                label: 'UCL',
                data: Array(labels.length).fill(ucl),
                borderColor: '#ef4444',
                borderDash: [5, 5],
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
            }, {
                label: 'CL',
                data: Array(labels.length).fill(cl),
                borderColor: '#22c55e',
                borderDash: [3, 3],
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
            }, {
                label: 'LCL',
                data: Array(labels.length).fill(lcl),
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
                x: { display: true, ticks: { maxTicksLimit: 10 } },
                y: { display: true }
            },
            plugins: { legend: { display: true } }
        }
    });

    // MR Chart
    const mrCtx = document.getElementById('mr-chart').getContext('2d');
    if (mrChart) mrChart.destroy();
    mrChart = new Chart(mrCtx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Moving Range',
                data: mrValues,
                borderColor: '#6366f1',
                borderWidth: 1.5,
                pointRadius: 0,
                fill: false,
            }, {
                label: 'Alarm (MR)',
                data: mrValues.map((v, i) => (v !== null && v > uclMr) ? v : null),
                borderColor: 'transparent',
                pointBackgroundColor: '#ef4444',
                pointRadius: 4,
                showLine: false,
            }, {
                label: 'UCL (MR)',
                data: Array(labels.length).fill(uclMr),
                borderColor: '#ef4444',
                borderDash: [5, 5],
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
            }, {
                label: 'CL (MR)',
                data: Array(labels.length).fill(clMr),
                borderColor: '#22c55e',
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
