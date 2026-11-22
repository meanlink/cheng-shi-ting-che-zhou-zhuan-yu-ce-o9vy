import {api, state} from '../api.js';
import {badge, empty} from '../components.js';
import {esc, fmt} from '../utils.js';

const statuses = {
    proposed: ['待处理', 'watch'], approved: ['已批准', 'good'], cancelled: ['已取消', ''],
    active: ['已启用', 'good'], closed: ['已结案', 'good'], submitted: ['待审核', 'watch'],
    returned: ['待补正', 'critical'], accepted: ['已通过', 'good'],
};
const operations = {closures: [], diversions: [], settlements: []};
const utcDay = () => new Date().toISOString().slice(0, 10);
const quantity = value => fmt(value, 2);

function select(name, options, placeholder) {
    return `<select name="${name}" required><option value="">${esc(placeholder)}</option>${options.map(([value, label]) =>
        `<option value="${esc(value)}">${esc(label)}</option>`).join('')}</select>`;
}

function note(name, placeholder) {
    return `<textarea name="${name}" required minlength="4" maxlength="500" rows="2" placeholder="${esc(placeholder)}"></textarea>`;
}

function jobForm(title, body, submit) {
    return `<section class="panel operation-form"><h2>${title}</h2><form class="stack" data-operation-create>
        ${body}<div class="form-status" role="status"></div><button class="button">${submit}</button></form></section>`;
}

function section(title, summary, registerTitle, records, form) {
    return `<section class="page operations"><div class="page-head"><div><h1>${title}</h1><p class="muted">${summary}</p></div></div>
        <div class="operation-layout ${form ? 'has-form' : ''}">
        <section class="operation-register"><h2>${registerTitle} <small>${records.length} 单</small></h2>
        ${records.join('') || empty('目前没有工单。相应岗位提交后，记录会显示在这里。')}</section>${form}</div></section>`;
}

function action(id, key, label) {
    return `<button type="button" class="icon-button operation-action" data-action="${key}" data-id="${id}">${label}</button>`;
}

function record(title, status, subtitle, details, message, actions) {
    const [label, tone] = statuses[status];
    return `<article class="panel operation-record"><div class="operation-record-head"><div><h3>${esc(title)}</h3>
        <p class="muted">${esc(subtitle)}</p></div>${badge(label, tone)}</div>
        <dl class="operation-metrics">${details.map(([key, value]) => `<div><dt>${esc(key)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>
        <div class="operation-message">${message}</div>${actions ? `<div class="operation-controls">${actions}</div>` : ''}</article>`;
}

function closuresPage() {
    const today = utcDay();
    const operator = state.user.role === 'operator';
    const supervisor = state.user.role === 'supervisor';
    const lots = state.lots.filter(lot => lot.status === 'active');
    const records = operations.closures.map(row => {
        const canApprove = supervisor && row.status === 'proposed' && row.starts_on >= today;
        const canCancel = (operator && row.status === 'proposed') || (supervisor && row.status !== 'cancelled');
        return record(row.lot_name, row.status, `${row.reference} · ${row.starts_on} 至 ${row.ends_on}`,
            [['额定车位', row.capacity], ['封控车位', row.blocked_spaces], ['封控后可用容量', row.effective_capacity]],
            `施工说明 · ${esc(row.reason)}`, (canApprove ? action(row.id, 'approve', '批准封控') : '') +
            (canCancel ? action(row.id, 'cancel', '取消封控') : ''));
    });
    const form = operator ? jobForm('提报临时封控', `
        <label>工单号<input name="reference" required minlength="4" maxlength="80" placeholder="如 WL-2607"></label>
        <label>停车场${select('lot_code', lots.map(lot => [lot.code, `${lot.name} · ${lot.capacity} 位`]), '选择停车场')}</label>
        <div class="operation-pair"><label>开始日<input name="starts_on" type="date" min="${today}" value="${today}" required></label>
        <label>结束日<input name="ends_on" type="date" min="${today}" value="${today}" required></label></div>
        <label>封控车位数<input name="blocked_spaces" type="number" min="1" step="1" required></label>
        <label>施工说明${note('reason', '记录封控区域、原因及现场安排')}</label>`, '提报工单') : '';
    return section('临时封控', '登记施工或活动占用的车位，批准后将封控窗口和可用容量提供给分流调度。运营日按 UTC 计。', '封控台账', records, form);
}

function diversionsPage() {
    const today = utcDay();
    const operator = state.user.role === 'operator';
    const usableClosures = operations.closures.filter(row => row.status === 'approved' && row.ends_on >= today);
    const records = operations.diversions.map(row => {
        const canActivate = operator && row.status === 'proposed' && row.service_day >= today;
        const canCancel = operator && (row.status === 'proposed' || (row.status === 'active' && row.service_day > today));
        return record(`${row.source_name} → ${row.target_name}`, row.status,
            `#${row.id} · ${row.service_day} · ${row.closure_reference} / ${row.forecast_code}`,
            [['预测周转（次）', quantity(row.forecast_turnover)], ['接收预留（位）', row.reserved_spaces],
                ['启用前可承诺（位）', row.target_headroom_at_activation ?? '待核算']],
            `现场安排 · ${esc(row.dispatch_note)}`, (canActivate ? action(row.id, 'activate', '核算并启用') : '') +
            (canCancel ? action(row.id, 'cancel', '撤销分流') : ''));
    });
    const hasPublished = state.forecasts.some(row => row.status === 'published');
    let form = '';
    if (operator) {
        form = usableClosures.length && hasPublished ? jobForm('安排跨场分流', `
            <label>来源封控单${select('closure_id', usableClosures.map(row => [row.id,
                `${row.reference} · ${row.lot_name} · 余 ${row.effective_capacity} 位`]), '选择已批准封控单')}</label>
            <label>运营日<input name="service_day" type="date" min="${today}" value="${today}" required></label>
            <label>公开预测<span data-forecast-options>${select('forecast_code', [], '先选封控单和运营日')}</span></label>
            <label>接收停车场<span data-target-options>${select('target_lot_code', [], '先选封控单')}</span></label>
            <label>接收预留车位<input name="reserved_spaces" type="number" min="1" step="1" required></label>
            <label>现场安排${note('dispatch_note', '填写入口引导、备班或车道安排')}</label>`, '生成分流单') :
            `<div class="panel operation-form">${empty('先取得封控批准和同场预测发布，再安排分流。')}<p><a href="#/closures">临时封控</a> · <a href="#/forecasts">预测工作台</a></p></div>`;
    }
    return section('跨场分流', '根据封控窗口和已发布预测排班。启用时按接收车场的实际余位核算当天可承诺的车位。', '分流清单', records, form);
}

function settlementsPage() {
    const analyst = state.user.role === 'analyst';
    const supervisor = state.user.role === 'supervisor';
    const open = operations.diversions.filter(row => row.status === 'active' && row.service_day <= utcDay() &&
        !operations.settlements.some(review => review.diversion_id === row.id && review.status !== 'returned'));
    const records = operations.settlements.map(row => record(`${row.source_name} → ${row.target_name}`, row.status,
        `${row.service_day} · 分流 #${row.diversion_id} · 第 ${row.revision} 版 · ${row.ledger_reference}`,
        [['预测 / 实际周转（次）', `${quantity(row.forecast_turnover)} / ${quantity(row.observed_turnover)}`],
            ['周转差（次）', quantity(row.turnover_delta)], ['周转偏差率', row.turnover_delta_pct === null ? '—' : `${quantity(row.turnover_delta_pct)}%`],
            ['预留（位） / 分流（辆）', `${row.reserved_spaces} / ${row.actual_diverted}`], ['实绩观测数', row.observation_count]],
        `分析 · ${esc(row.analysis_note)}${row.review_note ? `<br>审核 · ${esc(row.review_note)}` : ''}`,
        supervisor && row.status === 'submitted' ? action(row.id, 'accept', '通过并结案') + action(row.id, 'return', '退回复盘') : ''));
    let form = '';
    if (analyst) {
        form = open.length ? jobForm('提交结班实绩', `
            <label>分流单${select('diversion_id', open.map(row => [row.id,
                `#${row.id} · ${row.service_day} · ${row.source_name}`]), '选择待复盘分流单')}</label>
            <label>结班台账编号<input name="ledger_reference" required minlength="4" maxlength="80" placeholder="如 GATE-2307-PM"></label>
            <label>实际分流车辆<input name="actual_diverted" type="number" min="0" step="1" required></label>
            <label>偏差分析${note('analysis_note', '确认已结班，并解释现场实绩与预留有何差异')}</label>`, '提交复盘') :
            `<div class="panel operation-form">${empty('有已启用且运营日已到的分流单，或主管退回复盘时，即可提交。')}<p><a href="#/diversions">查看跨场分流</a></p></div>`;
    }
    return section('分流复盘', '结班后填写现场台账。系统从来源场站闸机观测汇总实际周转，主管通过后同步结案。', '实绩与审核', records, form);
}

const pages = {closures: closuresPage, diversions: diversionsPage, settlements: settlementsPage};
export const operationPages = Object.keys(pages);

export async function showOperation(page, mount, isCurrent) {
    mount(`<section class="page" role="status">正在读取运营台账…</section>`);
    try {
        const keys = page === 'closures' ? [page] : page === 'diversions' ? ['closures', page] : ['diversions', page];
        const values = await Promise.all(keys.map(key => api(`/operations/${key}`)));
        if (!isCurrent()) return;
        keys.forEach((key, index) => { operations[key] = values[index]; });
        mount(pages[page]());
        bindOperation(page, mount, isCurrent);
    } catch (error) {
        if (!isCurrent()) return;
        mount(`<section class="page"><p class="form-status" role="alert">${esc(error.message)}</p><button class="icon-button" data-operation-retry>重试</button></section>`);
        document.querySelector('[data-operation-retry]').onclick = () => showOperation(page, mount, isCurrent);
    }
}

function bindOperation(page, mount, isCurrent) {
    const form = document.querySelector('[data-operation-create]');
    if (form) {
        if (page === 'diversions') {
            const filterSources = async () => {
                const closure = operations.closures.find(row => row.id === Number(form.elements.closure_id.value));
                const day = form.elements.service_day.value;
                const host = form.querySelector('[data-forecast-options]');
                if (!closure || !day) {
                    host.innerHTML = select('forecast_code', [], '先选封控单和运营日');
                    return;
                }
                // 只允许选择该运营日“在用”的预测版本，旧版本会被后端拒绝。
                let inUseCode = null;
                try {
                    const versionRows = await api(`/forecasts/version-days?lot_code=${encodeURIComponent(closure.lot_code)}`);
                    const matched = versionRows.find(row => row.service_day === day);
                    inUseCode = matched?.forecast_code ?? null;
                } catch (error) {
                    host.innerHTML = select('forecast_code', [], `版本读取失败：${error.message}`);
                    return;
                }
                const forecast = state.forecasts.filter(row => row.status === 'published' && row.lot_code === closure.lot_code &&
                    row.predictions?.some(point => point.date === day) && row.code === inUseCode);
                host.innerHTML = select('forecast_code', forecast.map(row => [row.code, `${row.code}（当天在用）`]),
                    forecast.length ? '选择当天在用预测' : '该场站当天没有在用的已发布预测');
            };
            form.elements.closure_id.onchange = () => {
                const closure = operations.closures.find(row => row.id === Number(form.elements.closure_id.value));
                const day = form.elements.service_day;
                day.min = closure && closure.starts_on > utcDay() ? closure.starts_on : utcDay();
                day.max = closure?.ends_on ?? '';
                if (day.value < day.min || (day.max && day.value > day.max)) day.value = day.min;
                const lots = closure ? state.lots.filter(lot => lot.status === 'active' && lot.code !== closure.lot_code) : [];
                form.querySelector('[data-target-options]').innerHTML = select('target_lot_code', lots.map(lot => [lot.code, lot.name]), '选择接收场站');
                filterSources();
            };
            form.elements.service_day.onchange = filterSources;
        }
        submit(form, `/operations/${page}`, () => showOperation(page, mount, isCurrent));
    }
    document.querySelectorAll('[data-action]').forEach(button => {
        button.onclick = () => {
            const dialog = document.createElement('dialog');
            dialog.className = 'panel operation-dialog';
            dialog.innerHTML = `<h2>${esc(button.textContent)}</h2><form class="stack"><label>操作依据${note('note', '填写审核、安排或撤销的依据')}</label>
                <div class="form-status" role="status"></div><div class="operation-controls"><button class="button">确认</button><button type="button" class="icon-button" data-dismiss>返回</button></div></form>`;
            document.querySelector('#app').append(dialog);
            dialog.addEventListener('close', () => dialog.remove());
            dialog.querySelector('[data-dismiss]').onclick = () => dialog.close();
            submit(dialog.querySelector('form'), `/operations/${page}/${button.dataset.id}/${button.dataset.action}`, () => {
                if (dialog.open) dialog.close();
                if (isCurrent()) showOperation(page, mount, isCurrent);
            });
            dialog.showModal();
        };
    });
}

function submit(form, path, onSuccess) {
    form.onsubmit = async event => {
        event.preventDefault();
        const button = form.querySelector('button:not([type])');
        const status = form.querySelector('.form-status');
        const data = Object.fromEntries(new FormData(form));
        for (const key of ['blocked_spaces', 'closure_id', 'reserved_spaces', 'diversion_id', 'actual_diverted']) {
            if (key in data) data[key] = Number(data[key]);
        }
        button.disabled = true;
        status.textContent = '';
        try {
            await api(path, {method: 'POST', body: data});
            onSuccess();
        } catch (error) {
            status.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    };
}
