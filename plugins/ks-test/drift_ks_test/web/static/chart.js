/* KS Test 플러그인 차트 — v2.0 프리셋 + ECDF */

let valueChart = null;
let ksStatChart = null;
let pvalueChart = null;
let ecdfChart = null;
let currentPreset = 'standard';

const PRESETS = {
    quick: { window_size: 30, alpha: 0.05, correction: 'none', update_reference: false, remove_outliers: false, method: 'asymptotic', reference_ratio: 0.5 },
    standard: { window_size: 100, alpha: 0.05, correction: 'bh', update_reference: true, remove_outliers: true, method: 'asymptotic', reference_ratio: 0.5 },
    precision: { window_size: 200, alpha: 0.01, correction: 'bonferroni', update_reference: true, remove_outliers: true, method: 'exact', reference_ratio: 0.5 },
    streaming: { window_size: 100, alpha: 0.05, correction: 'bh', update_reference: true, remove_outliers: false, method: 'asymptotic', reference_ratio: 0.5 },
    small_sample: { window_size: 30, alpha: 0.10, correction: 'none', update_reference: false, remove_outliers: false, method: 'bootstrap', reference_ratio: 0.5 },
};

function selectPreset(name) {
    currentPreset = name;
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    const btn = document.querySelector(`[data-preset="${name}"]`);
    if (btn) btn.classList.add('active');

    if (name !== 'custom' && PRESETS[name]) {
        applyPreset(PRESETS[name]);
    }
    if (name !== 'custom') runExample();
}

function applyPreset(p) {
    document.getElementById('param-window').value = p.window_size;
    document.getElementById('param-alpha').value = p.alpha;
    document.getElementById('param-ratio').value = p.reference_ratio;
    document.querySelector(`input[name="correction"][value="${p.correction}"]`).checked = true;
    document.getElementById('param-update-ref').checked = p.update_reference;
    document.getElementById('param-remove-outliers').checked = p.remove_outliers;
    document.querySelector(`input[name="method"][value="${p.method}"]`).checked = true;
}

function getParams() {
    return {
        window_size: parseInt(document.getElementById('param-window').value),
        alpha: parseFloat(document.getElementById('param-alpha').value),
        reference_ratio: parseFloat(document.getElementById('param-ratio').value),
        correction: document.querySelector('input[name="correction"]:checked').value,
        update_reference: document.getElementById('param-update-ref').checked,
        remove_outliers: document.getElementById('param-remove-outliers').checked,
        method: document.querySelector('input[name="method"]:checked').value,
    };
}

function runExample() {
    const p = getParams();
    const qs = new URLSearchParams({
        preset: currentPreset,
        window_size: p.window_size,
        alpha: p.alpha,
        reference_ratio: p.reference_ratio,
        correction: p.correction,
        update_reference: p.update_reference,
        remove_outliers: p.remove_outliers,
        method: p.method,
    });

    fetch(`/drift/ks_test/api/example?${qs}`)
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

    let alarmMask = [], ksSeries = [], correctedPSeries = [];
    let alpha = 0.05, correction = 'bh';
    let ecdfRefX = [], ecdfRefY = [], ecdfTestX = [], ecdfTestY = [];

    if (events.length > 0 && events[0].detail) {
        const d = events[0].detail;
        alarmMask = d.alarm_mask || [];
        ksSeries = d.ks_series || [];
        correctedPSeries = d.corrected_pvalue_series || d.pvalue_series || [];
        alpha = d.alpha || 0.05;
        correction = d.correction || 'none';
        ecdfRefX = d.ecdf_ref_x || [];
        ecdfRefY = d.ecdf_ref_y || [];
        ecdfTestX = d.ecdf_test_x || [];
        ecdfTestY = d.ecdf_test_y || [];
    }

    // 1. Value Chart
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
                label: 'Drift Alarm',
                data: values.map((v, i) => alarmMask[i] ? v : null),
                borderColor: 'transparent',
                pointBackgroundColor: '#ef4444',
                pointRadius: 3,
                showLine: false,
            }]
        },
        options: {
            responsive: true,
            scales: { x: { ticks: { maxTicksLimit: 8 } } },
            plugins: { legend: { display: true } }
        }
    });

    // 2. ECDF Chart
    const ecdfCtx = document.getElementById('ecdf-chart').getContext('2d');
    if (ecdfChart) ecdfChart.destroy();
    const ecdfRefData = ecdfRefX.map((x, i) => ({x: x, y: ecdfRefY[i]}));
    const ecdfTestData = ecdfTestX.map((x, i) => ({x: x, y: ecdfTestY[i]}));
    ecdfChart = new Chart(ecdfCtx, {
        type: 'scatter',
        data: {
            datasets: [{
                label: 'Reference ECDF',
                data: ecdfRefData,
                borderColor: '#3b82f6',
                backgroundColor: 'transparent',
                borderWidth: 2,
                pointRadius: 0,
                showLine: true,
                stepped: 'after',
            }, {
                label: 'Test ECDF',
                data: ecdfTestData,
                borderColor: '#f97316',
                backgroundColor: 'transparent',
                borderWidth: 2,
                pointRadius: 0,
                showLine: true,
                stepped: 'after',
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: { title: { display: true, text: 'Value' } },
                y: { title: { display: true, text: 'Cumulative Probability' }, min: 0, max: 1 },
            },
            plugins: { legend: { display: true } }
        }
    });

    // 3. D-statistic Chart
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
            scales: { x: { ticks: { maxTicksLimit: 8 } }, y: { beginAtZero: true } },
            plugins: { legend: { display: true } }
        }
    });

    // 4. p-value Chart (corrected)
    const pCtx = document.getElementById('pvalue-chart').getContext('2d');
    if (pvalueChart) pvalueChart.destroy();
    const pvalLog = correctedPSeries.map(p => p > 0 && p < 1 ? -Math.log10(p) : 0);
    const alphaLine = -Math.log10(alpha);
    pvalueChart = new Chart(pCtx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: `-log10(corrected p) [${correction}]`,
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
            scales: { x: { ticks: { maxTicksLimit: 8 } }, y: { beginAtZero: true } },
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
        Math.min(...events.map(e => e.detail.corrected_p_value || e.detail.p_value || 1)).toExponential(2);
    document.getElementById('stat-type').textContent =
        events[0].detail.drift_type || '-';

    const tbody = document.querySelector('#events-table tbody');
    tbody.innerHTML = '';
    for (const e of events) {
        const d = e.detail;
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${e.detected_at}</td>
            <td>${(d.d_statistic || 0).toFixed(4)}</td>
            <td>${(d.p_value || 0).toExponential(2)}</td>
            <td>${(d.corrected_p_value || d.p_value || 0).toExponential(2)}</td>
            <td><span class="severity-${e.severity}">${e.severity}</span></td>
            <td>${d.drift_type || '-'}</td>
            <td>${e.message}</td>
        `;
        tbody.appendChild(tr);
    }
}
