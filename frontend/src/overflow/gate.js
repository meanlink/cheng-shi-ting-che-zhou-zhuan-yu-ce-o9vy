import {empty} from '../components.js';
import {esc, fmt} from '../utils.js';
import {utcClock} from './labels.js';
import {pageHeading, summary, windowSelector} from './shared.js';

function gateForm(window) {
    const exitOnly = window.status === 'paused' || Date.now() >= Date.parse(window.ends_at);
    return `<form class="stack overflow-gate-form" data-overflow-form="gate" data-window-id="${window.id}">
        <label>闸机单号<input name="receipt" minlength="3" maxlength="48" required placeholder="GATE-0701"></label>
        <label>进场车辆<input name="admitted" type="number" min="0" max="10000" value="0" required ${exitOnly ? 'readonly' : ''}></label>
        <label>离场车辆<input name="released" type="number" min="0" max="10000" value="0" required></label>
        <button class="button">登记流水</button>
        <div class="form-status" role="status"></div>
    </form>`;
}

function batchTable(batches) {
    if (!batches.length) return empty('当前窗口还没有闸机流水。');
    return `<div class="overflow-table"><table><thead><tr>
        <th>闸机单号</th><th>登记时间 · UTC</th><th>进场</th><th>离场</th><th>登记后场内</th>
    </tr></thead><tbody>${batches.map(row => `<tr><td class="code">${esc(row.receipt)}</td>
        <td>${utcClock(row.recorded_at)}</td><td>${fmt(row.admitted)}</td><td>${fmt(row.released)}</td>
        <td>${fmt(row.parked_after)}</td></tr>`).join('')}</tbody></table></div>`;
}

export function gatePage(windows, data, role) {
    const heading = pageHeading('溢流闸机', '核对接收场的实时收车与离场流水。');
    if (!data) return heading + empty('开放入口后，可在此登记闸机流水。');
    const {window, batches} = data;
    const paused = window.status === 'paused';
    const expired = window.status === 'open' && Date.now() >= Date.parse(window.ends_at);
    return `${heading}${windowSelector(windows, window.id)}${summary(window)}
        ${paused ? `<p class="overflow-warning">暂停收车 · ${esc(window.pause_reason)}。仍可登记离场。</p>` : ''}
        ${expired ? '<p class="overflow-warning">收车时段已结束，仍可登记离场。</p>' : ''}
        ${role === 'operator' && ['open','paused'].includes(window.status) ? `<section class="overflow-panel">
            <h2>登记闸机批次</h2><p class="muted">同时有进出记录时，先核销离场再计算可用车位。</p>${gateForm(window)}</section>` : ''}
        <section class="overflow-panel"><div class="overflow-section-title"><h2>最近流水</h2><a href="#/overflow-dispatch">查看开放计划</a></div>
            ${batchTable(batches)}</section>`;
}
