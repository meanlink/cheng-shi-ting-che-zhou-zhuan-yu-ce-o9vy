import {api, state} from '../api.js';
import {esc} from '../utils.js';
import {closeoutPage} from './closeout.js';
import {dispatchPage} from './dispatch.js';
import {gatePage} from './gate.js';
import {windowActions} from './labels.js';
import {bindForecastTarget} from './request-form.js';

export const overflowNavigation = [
    ['overflow-dispatch', '溢流调度', '▤'],
    ['overflow-gate', '溢流闸机', '⇄'],
    ['overflow-closeout', '交班盘点', '▣'],
];

const base = '/overflow/windows';
const gateStatuses = ['open', 'paused', 'ended', 'reconciled'];
const closeoutStatuses = ['ended', 'reconciled'];
const toUtc = value => new Date(`${value}Z`).toISOString();

function notice(message) {
    return message ? `<div class="overflow-feedback" role="status">${esc(message)}</div>` : '';
}

function payload(form) {
    const body = Object.fromEntries(new FormData(form));
    for (const key of ['bay_limit', 'admitted', 'released', 'counted_admitted', 'counted_released']) {
        if (key in body) body[key] = Number(body[key]);
    }
    for (const key of ['starts_at', 'ends_at']) {
        if (key in body) body[key] = toUtc(body[key]);
    }
    return body;
}

function endpoint(form) {
    const {overflowForm, windowId, path} = form.dataset;
    if (overflowForm === 'decision') return path;
    if (overflowForm === 'gate') return `${base}/${windowId}/gate`;
    if (overflowForm === 'tally') return `${base}/${windowId}/closeout`;
    return base;
}

function bindForms(root, reload) {
    bindForecastTarget(root.querySelector('[data-overflow-form="window"]'));
    for (const form of root.querySelectorAll('[data-overflow-form]')) {
        form.addEventListener('submit', async event => {
            event.preventDefault();
            const button = form.querySelector('button:not([type="button"])');
            const status = form.querySelector('[role="status"]');
            button.disabled = true;
            status.textContent = '';
            try {
                const result = await api(endpoint(form), {method: 'POST', body: payload(form)});
                form.closest('dialog')?.close();
                await reload(result.status === 'flagged' ? '已保存差异版本，请核对台账。' : '已保存。');
            } catch (error) {
                status.textContent = error.message;
                status.classList.add('error');
            } finally {
                button.disabled = false;
            }
        });
    }
}

function bindDecisions(root) {
    const dialog = root.querySelector('[data-decision-dialog]');
    if (!dialog) return;
    const form = dialog.querySelector('form');
    dialog.querySelector('[data-dismiss]').addEventListener('click', () => dialog.close());
    for (const button of root.querySelectorAll('[data-window-action], [data-review]')) {
        button.addEventListener('click', () => {
            const {windowAction, review, windowId, revisionId} = button.dataset;
            const [title, detail] = windowAction ? windowActions[windowAction] : [button.textContent,
                review === 'accept' ? '通过后关闭该窗口的交班盘点。' : '退回后由分析员提交新版本。'];
            form.reset();
            form.querySelector('h2').textContent = title;
            form.querySelector('p').textContent = detail;
            form.querySelector('[role="status"]').textContent = '';
            form.dataset.path = windowAction ? `${base}/${windowId}/decision/${windowAction}` :
                `${base}/${windowId}/closeout/${revisionId}/${review}`;
            dialog.showModal();
        });
    }
}

export async function showOverflow(page, shell, isCurrent, message = '') {
    try {
        const windows = await api(base);
        const first = page === 'overflow-dispatch';
        const isGate = page === 'overflow-gate';
        const choices = windows.filter(row => (isGate ? gateStatuses : closeoutStatuses).includes(row.status));
        const selected = Number(location.hash.split('/')[2]);
        const current = choices.find(row => row.id === selected) ?? choices[0];
        const data = !first && current ? await api(`${base}/${current.id}/${isGate ? 'gate' : 'closeout'}`) : null;
        if (!isCurrent()) return;
        const {role} = state.user;
        const render = isGate ? gatePage : closeoutPage;
        const content = first ? dispatchPage(windows, {role, forecasts: state.forecasts, lots: state.lots}) :
            render(choices, data, role);
        shell(`<div class="overflow-workspace">${notice(message)}${content}</div>`);
        const root = document.querySelector('.overflow-workspace');
        root.querySelector('[data-window-picker]')?.addEventListener('change', event => {
            location.hash = `#/${page}/${event.target.value}`;
        });
        bindForms(root, feedback => showOverflow(page, shell, isCurrent, feedback));
        bindDecisions(root);
    } catch (error) {
        if (isCurrent()) shell(`<div class="form-status error" role="alert">${esc(error.message)}</div>`);
    }
}
