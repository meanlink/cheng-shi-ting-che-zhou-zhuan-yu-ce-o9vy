import {badge, stat} from '../components.js';
import {esc, fmt} from '../utils.js';
import {utcRange, windowStatus} from './labels.js';

export const statusBadge = (status, dictionary = windowStatus) => badge(...dictionary[status]);

export function pageHeading(title, description) {
    return `<header class="overflow-heading"><h1>${esc(title)}</h1><p>${esc(description)}</p></header>`;
}

export function windowSelector(windows, selectedId) {
    return `<label class="overflow-picker">调度窗口<select name="window_id" data-window-picker>
        ${windows.map(row => `<option value="${row.id}" ${row.id === selectedId ? 'selected' : ''}>
            ${esc(row.reference)} · ${esc(row.target_name)} · ${windowStatus[row.status][0]}</option>`).join('')}
    </select></label>`;
}

export function summary(window) {
    return `<div class="overflow-summary">
        <div><span class="code">${esc(window.reference)}</span><h2>${esc(window.target_name)}</h2>
        <p>${esc(window.source_name)} → ${esc(window.target_name)}</p><small>${utcRange(window)}</small></div>
        ${statusBadge(window.status)}
    </div><div class="overflow-stats">
        ${stat('场内车辆', `${fmt(window.parked)} 辆`, `配额 ${fmt(window.bay_limit)} 位`)}
        ${stat('累计进场', `${fmt(window.admitted)} 辆`)}
        ${stat('累计离场', `${fmt(window.released)} 辆`)}
        ${stat('峰值在场', `${fmt(window.peak_parked)} 辆`)}
    </div>`;
}

export function decisionDialog() {
    return `<dialog class="overflow-dialog" data-decision-dialog>
        <form data-overflow-form="decision" class="stack">
            <h2></h2><p class="muted"></p>
            <label>处理说明<textarea name="note" minlength="4" maxlength="240" rows="3" required></textarea></label>
            <div class="form-status" role="status"></div>
            <div class="overflow-actions"><button type="button" class="button secondary" data-dismiss>取消</button>
                <button class="button">确认提交</button></div>
        </form></dialog>`;
}
