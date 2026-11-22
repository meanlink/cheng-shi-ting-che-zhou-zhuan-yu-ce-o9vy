import {empty} from '../components.js';
import {esc, fmt} from '../utils.js';
import {allowedActions, utcRange, windowActions} from './labels.js';
import {decisionDialog, pageHeading, statusBadge} from './shared.js';
import {requestForm} from './request-form.js';

function windowCard(window, role) {
    const actions = allowedActions(role, window.status);
    const gateVisible = ['open', 'paused', 'ended', 'reconciled'].includes(window.status);
    const closeoutVisible = ['ended', 'reconciled'].includes(window.status);
    return `<article class="overflow-card" data-window-card="${window.id}">
        <div class="overflow-card-top"><span class="code">${esc(window.reference)}</span>${statusBadge(window.status)}</div>
        <h3>${esc(window.source_name)} <span aria-hidden="true">→</span> ${esc(window.target_name)}</h3>
        <p class="overflow-time">${utcRange(window)}</p>
        <dl><div><dt>溢流配额</dt><dd>${fmt(window.bay_limit)} 位</dd></div>
            <div><dt>来源日周转预测</dt><dd>${fmt(window.forecast_turnover, 2)} 次</dd></div>
            <div><dt>预测编号</dt><dd class="code">${esc(window.forecast_code)}</dd></div></dl>
        <p class="muted">${esc(window.reason)}</p>
        ${window.status === 'paused' ? `<p class="overflow-warning">${esc(window.pause_reason)}</p>` : ''}
        <div class="overflow-actions">
            ${actions.map(action => `<button class="button ${['cancel', 'pause'].includes(action) ? 'secondary' : ''}"
                data-window-action="${action}" data-window-id="${window.id}">${windowActions[action][0]}</button>`).join('')}
            ${gateVisible ? `<a class="button secondary" href="#/overflow-gate/${window.id}">查看闸机</a>` : ''}
            ${closeoutVisible ? `<a class="button secondary" href="#/overflow-closeout/${window.id}">查看交班盘点</a>` : ''}
        </div>
    </article>`;
}

export function dispatchPage(windows, {role, forecasts, lots}) {
    return `${pageHeading('溢流调度', '依据已发布周转预测安排接收场，按运营时段交接车位配额。')}
        <div class="overflow-dispatch ${role === 'operator' ? 'overflow-dispatch-split' : ''}">
            <section aria-label="开放计划"><div class="overflow-section-title"><h2>开放计划</h2><span>${windows.length} 个窗口</span></div>
                ${windows.map(row => windowCard(row, role)).join('') || empty('暂无溢流窗口。')}</section>
            ${role === 'operator' ? `<aside class="overflow-panel overflow-intake"><h2>新建溢流窗口</h2>
                <p class="muted">开放时段为同一 UTC 运营日内的 15 分钟至 8 小时。</p>${requestForm(forecasts, lots)}</aside>` : ''}
        </div>${decisionDialog()}`;
}
