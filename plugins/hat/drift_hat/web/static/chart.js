/* HAT 플러그인 전문가 차트 — v2.0 (ADWIN) 스크롤 지원 */

let meanChart = null;
let windowChart = null;
let _allData = [];
let _allEvents = [];
let _viewSize = 288;
let _scrollPos = 0;

function loadExpertFromCache() {
    fetch('/drift/hat/api/chart-data')
        .then(r => r.json())
        .then(resp => {
            _allData = resp.data || [];
            _allEvents = resp.drift_events || [];
            _scrollPos = 0;
            const scroll = document.getElementById('expertScroll');
            if (scroll) scroll.value = 0;
            renderView();
            renderResults(_allEvents);
        })
        .catch(err => console.error('Expert load error:', err));
}

function getParams() {
    const deltaEl = document.getElementById('param-delta');
    const baselineEl = document.getElementById('param-baseline');
    return {
        delta: deltaEl ? parseFloat(deltaEl.value) : 0.002,
        baseline_ratio: baselineEl ? parseFloat(baselineEl.value) : 0.3,
    };
}

function onExpertScroll(val) {
    _scrollPos = val / 1000;
    renderView();
}

function setExpertRange(size) {
    _viewSize = size;
    document.querySelectorAll('.expert-range-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    renderView();
}

function renderView() {
    if (!_allData || _allData.length === 0) return;

    let data;
    if (_viewSize === 0 || _viewSize >= _allData.length) {
        data = _allData;
    } else {
        const maxStart = Math.max(0, _allData.length - _viewSize);
        const start = Math.round(maxStart * _scrollPos);
        data = _allData.slice(start, start + _viewSize);
    }
    renderExpertCharts(data);
}

function renderExpertCharts(data) {
    if (!data || data.length === 0) return;

    const labels = data.map(d => {
        const ts = new Date(d.timestamp);
        return ts.toLocaleString('ko-KR', {month:'2-digit', day:'2-digit', hour:'2-digit'});
    });

    const values = data.map(d => d.value);
    const meanSeries = data.map(d => d.running_mean !== undefined ? d.running_mean : null);
    const windowSizeSeries = data.map(d => d.window_size !== undefined ? d.window_size : null);

    // ---- Running Mean Chart ----
    const meanCtx = document.getElementById('mean-chart');
    if (!meanCtx) return;
    if (meanChart) meanChart.destroy();

    meanChart = new Chart(meanCtx.getContext('2d'), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Value',
                    data: values,
                    borderColor: '#94a3b8',
                    borderWidth: 1,
                    pointRadius: 0,
                    fill: false,
                },
                {
                    label: 'Running Mean (ADWIN)',
                    data: meanSeries,
                    borderColor: '#3b82f6',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: false,
                },
            ]
        },
        options: {
            responsive: true,
            animation: false,
            scales: {
                x: { display: true, ticks: { maxTicksLimit: 15 } },
                y: { display: true, title: { display: true, text: 'Value / Mean' } }
            },
            plugins: { legend: { display: true } }
        }
    });

    // ---- Window Size Chart ----
    const windowCtx = document.getElementById('window-chart');
    if (!windowCtx) return;
    if (windowChart) windowChart.destroy();

    windowChart = new Chart(windowCtx.getContext('2d'), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'ADWIN Window Size',
                data: windowSizeSeries,
                borderColor: '#8b5cf6',
                backgroundColor: 'rgba(139, 92, 246, 0.1)',
                borderWidth: 2,
                pointRadius: 0,
                fill: true,
            }]
        },
        options: {
            responsive: true,
            animation: false,
            scales: {
                x: { display: true, ticks: { maxTicksLimit: 15 } },
                y: { display: true, beginAtZero: true, title: { display: true, text: 'Window Size' } }
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
    if (el('stat-severity')) {
        el('stat-severity').textContent = events.reduce((max, e) =>
            e.severity === 'critical' ? 'critical' : (max === 'critical' ? max : e.severity), 'normal');
    }

    const tbody = document.querySelector('#events-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    for (const e of events) {
        const d = e.detail || {};
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${e.detected_at || '-'}</td>
            <td>${d.window_before !== undefined ? d.window_before : '-'}</td>
            <td>${d.window_after !== undefined ? d.window_after : '-'}</td>
            <td>${e.score.toFixed(2)}</td>
            <td><span class="severity-${e.severity}">${e.severity}</span></td>
        `;
        tbody.appendChild(tr);
    }
}
