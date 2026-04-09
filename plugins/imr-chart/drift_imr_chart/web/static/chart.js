/* I-MR Chart 플러그인 전문가 차트 — v2.0 스크롤 지원 */

let imrChartExpert = null;
let _allData = [];       // 전체 데이터 보관
let _viewSize = 288;     // 현재 표시 범위 (0=전체)
let _scrollPos = 0;      // 스크롤 위치 (0~1)

function loadExpertFromCache() {
    fetch('/drift/imr_chart/api/chart-data')
        .then(r => r.json())
        .then(resp => {
            _allData = resp.data || [];
            _scrollPos = 0;
            document.getElementById('expertScroll').value = 0;
            renderView();
            renderResults(resp.drift_events || []);
        })
        .catch(err => console.error('Expert load error:', err));
}

function getParams() {
    return {
        baseline_ratio: parseFloat(document.getElementById('param-baseline').value),
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
    const ucl = data[0].ucl || 0;
    const cl = data[0].cl || 0;
    const lcl = data[0].lcl || 0;

    const ctx = document.getElementById('imr-chart-expert');
    if (!ctx) return;
    if (imrChartExpert) imrChartExpert.destroy();

    const datasets = [
        {
            label: 'Individual (X)',
            data: values,
            borderColor: '#0f172a',
            borderWidth: 1.5,
            pointRadius: values.map(v => (v > ucl || v < lcl) ? 5 : 1),
            pointBackgroundColor: values.map(v => (v > ucl || v < lcl) ? '#ef4444' : '#0f172a'),
            fill: false,
        },
        {
            label: 'UCL (' + ucl.toFixed(2) + ')',
            data: Array(labels.length).fill(ucl),
            borderColor: '#ef4444',
            borderDash: [6, 3],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
        },
        {
            label: 'CL (' + cl.toFixed(2) + ')',
            data: Array(labels.length).fill(cl),
            borderColor: '#22c55e',
            borderDash: [4, 4],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
        },
        {
            label: 'LCL (' + lcl.toFixed(2) + ')',
            data: Array(labels.length).fill(lcl),
            borderColor: '#ef4444',
            borderDash: [6, 3],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
        },
    ];

    imrChartExpert = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: { labels: labels, datasets: datasets },
        options: {
            responsive: true,
            animation: false,
            scales: {
                x: { display: true, ticks: { maxTicksLimit: 15 } },
                y: { display: true, title: { display: true, text: 'Individual Value' } }
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
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${e.detected_at || '-'}</td>
            <td>${e.score.toFixed(2)}</td>
            <td><span class="severity-${e.severity}">${e.severity}</span></td>
            <td>${e.message || '-'}</td>
        `;
        tbody.appendChild(tr);
    }
}
