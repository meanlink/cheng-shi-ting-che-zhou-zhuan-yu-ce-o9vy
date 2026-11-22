import {empty} from '../components.js';
import {esc, fmt} from '../utils.js';
import {closeoutStatus} from './labels.js';
import {decisionDialog, pageHeading, statusBadge, summary, windowSelector} from './shared.js';

function tallyForm(window) {
    return `<section class="overflow-panel"><h2>提交交班盘点</h2>
        <p class="muted">录入独立交班台账的总进场和总离场，以便与闸机累计数核对。</p>
        <form class="stack" data-overflow-form="tally" data-window-id="${window.id}">
            <div class="overflow-fields overflow-fields-three">
                <label>台账编号<input name="ledger_reference" minlength="3" maxlength="48" required></label>
                <label>台账进场<input name="counted_admitted" type="number" min="0" max="1000000000" required></label>
                <label>台账离场<input name="counted_released" type="number" min="0" max="1000000000" required></label>
            </div>
            <label>盘点说明<textarea name="note" rows="2" minlength="4" maxlength="240" required></textarea></label>
            <div class="form-status" role="status"></div><button class="button">提交盘点</button>
        </form></section>`;
}

function revisionCard(window, row, canReview) {
    const delta = value => `${value > 0 ? '+' : ''}${fmt(value)} 辆`;
    return `<article class="overflow-card" data-revision="${row.revision}">
        <div class="overflow-card-top"><span class="code">${esc(row.ledger_reference)} · 版本 ${row.revision}</span>
            ${statusBadge(row.status, closeoutStatus)}</div>
        <dl><div><dt>台账进场</dt><dd>${fmt(row.counted_admitted)} 辆</dd></div>
            <div><dt>台账离场</dt><dd>${fmt(row.counted_released)} 辆</dd></div>
            <div><dt>进场差额</dt><dd>${delta(row.admission_delta)}</dd></div>
            <div><dt>离场差额</dt><dd>${delta(row.release_delta)}</dd></div></dl>
        <p>${esc(row.note)}</p>${row.review_note ? `<p class="muted">${esc(row.review_note)}</p>` : ''}
        ${row.status === 'flagged' ? '<p class="overflow-warning">台账与闸机流水有差异。核对原始凭证后提交新版本。</p>' : ''}
        ${canReview ? `<div class="overflow-actions">
            <button class="button" data-review="accept" data-window-id="${window.id}" data-revision-id="${row.id}">通过并结案</button>
            <button class="button secondary" data-review="return" data-window-id="${window.id}" data-revision-id="${row.id}">退回盘点</button>
        </div>` : ''}
    </article>`;
}

export function closeoutPage(windows, data, role) {
    const heading = pageHeading('交班盘点', '核对现场台账与闸机流水，保留差异和复核记录。');
    if (!data) return heading + empty('结束窗口后，可在此提交交班盘点。');
    const {window, revisions} = data;
    const latest = revisions[0];
    const ended = window.status === 'ended';
    const canSubmit = role === 'analyst' && ended && (!latest || ['flagged','returned'].includes(latest.status));
    return `${heading}${windowSelector(windows, window.id)}${summary(window)}
        <div class="overflow-section-title"><h2>盘点记录</h2><a href="#/overflow-gate/${window.id}">核对闸机流水</a></div>
        ${revisions.map((row, index) => revisionCard(window, row,
            index === 0 && role === 'supervisor' && ended && row.status === 'ready')).join('') || empty('当前窗口还没有交班盘点。')}
        ${canSubmit ? tallyForm(window) : ''}${decisionDialog()}`;
}
