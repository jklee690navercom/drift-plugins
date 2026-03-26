/* X-bar/R Chart 플러그인 차트 */

let xbarChart = null;
let rChart = null;

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
    fetch('/drift/xbar_r_chart/api/example')
        .then(r => r.json())
        .then(resp => {
            renderCharts(resp.data, resp.events);
            renderResults(resp.events);
        })
        .catch(err => console.error('Error:', err));
}

function renderCharts(data, events) {
    let xbarValues = [], rValues = [];
    let uclXbar = 0, lclXbar = 0, clXbar = 0;
    let uclR = 0, lclR = 0, clR = 0;
    let alarmMaskXbar = [], alarmMaskR = [];
    let subgroupSize = 5;

    if (events.length > 0 && events[0].detail) {
        const d = events[0].detail;
        xbarValues = d.xbar_values || [];
        rValues = d.r_values || [];
        uclXbar = d.ucl_xbar;
        lclXbar = d.lcl_xbar;
        clXbar = d.cl_xbar;
        uclR = d.ucl_r;
        lclR = d.lcl_r;
        clR = d.cl_r;
        alarmMaskXbar = d.alarm_mask_xbar || [];
        alarmMaskR = d.alarm_mask_r || [];
        subgroupSize = d.subgroup_size || 5;
    }

    const labels = xbarValues.map((_, i) => 'Group ' + (i + 1));

    // X-bar Chart
    const xbarCtx = document.getElementById('xbar-chart').getContext('2d');
    if (xbarChart) xbarChart.destroy();
    xbarChart = new Chart(xbarCtx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'X-bar',
                data: xbarValues,
                borderColor: '#0f172a',
                borderWidth: 1.5,
                pointRadius: 2,
                fill: false,
            }, {
                label: 'Alarm (X-bar)',
                data: xbarValues.map((v, i) => alarmMaskXbar[i] ? v : null),
                borderColor: 'transparent',
                pointBackgroundColor: '#ef4444',
                pointRadius: 5,
                showLine: false,
            }, {
                label: 'UCL',
                data: Array(labels.length).fill(uclXbar),
                borderColor: '#ef4444',
                borderDash: [5, 5],
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
            }, {
                label: 'CL',
                data: Array(labels.length).fill(clXbar),
                borderColor: '#22c55e',
                borderDash: [3, 3],
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
            }, {
                label: 'LCL',
                data: Array(labels.length).fill(lclXbar),
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
                x: { display: true, ticks: { maxTicksLimit: 15 } },
                y: { display: true }
            },
            plugins: { legend: { display: true } }
        }
    });

    // R Chart
    const rCtx = document.getElementById('r-chart').getContext('2d');
    if (rChart) rChart.destroy();
    rChart = new Chart(rCtx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Range (R)',
                data: rValues,
                borderColor: '#6366f1',
                borderWidth: 1.5,
                pointRadius: 2,
                fill: false,
            }, {
                label: 'Alarm (R)',
                data: rValues.map((v, i) => alarmMaskR[i] ? v : null),
                borderColor: 'transparent',
                pointBackgroundColor: '#ef4444',
                pointRadius: 5,
                showLine: false,
            }, {
                label: 'UCL (R)',
                data: Array(labels.length).fill(uclR),
                borderColor: '#ef4444',
                borderDash: [5, 5],
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
            }, {
                label: 'CL (R)',
                data: Array(labels.length).fill(clR),
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
