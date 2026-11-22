import {api, state} from '../api.js';
import {badge, empty} from '../components.js';
import {esc} from '../utils.js';

let versionDays = [];
let loadError = '';

// 浏览器端生成 request_id：换版未收到回执时，同号重试由后端幂等去重。
function makeRequestId() {
    const rand = crypto.getRandomValues(new Uint8Array(6));
    const hex = Array.from(rand, b => b.toString(16).padStart(2, '0')).join('');
    return `sw-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}-${hex}`;
}

export async function loadVersionDays(lotCode) {
    versionDays = [];
    loadError = '';
    try {
        versionDays = await api(`/forecasts/version-days${lotCode ? `?lot_code=${encodeURIComponent(lotCode)}` : ''}`);
    } catch (error) {
        loadError = error.message;
    }
    return versionDays;
}

function lockBadge(row) {
    if (!row.locked) return badge('可换版', 'good');
    if (row.lock_reason === 'diversion_closed') return badge('结案冻结', 'critical');
    return badge('分流锁定', 'watch');
}

export function versionPanel(lotCode) {
    const supervisor = state.user?.role === 'supervisor';
    if (loadError) {
        return `<section class="card version-panel"><div class="card-head"><div><span class="eyebrow">逐日版本</span><h2>每天在用的预测版本</h2></div></div>${empty(loadError)}</section>`;
    }
    const rows = lotCode ? versionDays.filter(r => r.lot_code === lotCode) : versionDays;
    return `<section class="card version-panel">
        <div class="card-head">
            <div><span class="eyebrow">逐日版本</span><h2>每天在用的预测版本与锁定原因</h2>
            <p class="muted version-hint">已启用或结案分流的运营日自动锁定，沿用换版前的原版数字；其余日期主管可逐日切换到新版。</p></div>
            <span class="muted">${rows.length} 个运营日</span>
        </div>
        <div class="table-wrap">
        <table class="version-table">
            <thead><tr><th>运营日 (UTC)</th><th>场站</th><th>在用版本</th><th>状态 / 锁定原因</th><th>可切换版本</th>${supervisor ? '<th>逐日换版</th>' : ''}</tr></thead>
            <tbody>${rows.map(row => {
                const options = [row.forecast_code, ...row.alternatives.map(a => a.forecast_code)].filter(Boolean);
                const canSwitch = supervisor && !row.locked && options.length > 1;
                return `<tr class="${row.locked ? 'is-locked' : ''}">
                    <td><strong>${esc(row.service_day)}</strong>${row.explicitly_switched ? '<small>已人工换版</small>' : '<small>默认版本</small>'}</td>
                    <td>${esc(row.lot_code)}<small>${esc(row.lot_name)}</small></td>
                    <td><code>${esc(row.forecast_code || '—')}</code></td>
                    <td>${lockBadge(row)}${row.locked ? `<small class="lock-note">${esc(row.lock_reason_label || '已锁定')}</small>` : '<small>当天没有启用/结案分流</small>'}</td>
                    <td>${row.alternatives.length ? row.alternatives.map(a => `<code class="alt-code">${esc(a.forecast_code)}</code>`).join('') : '<small>无</small>'}</td>
                    ${supervisor ? `<td>${canSwitch ? `
                        <div class="switch-controls">
                            <select data-switch-select data-day="${esc(row.service_day)}" data-lot="${esc(row.lot_code)}">
                                ${options.map(code => `<option value="${esc(code)}" ${code === row.forecast_code ? 'selected' : ''}>${esc(code)}</option>`).join('')}
                            </select>
                            <button type="button" class="button secondary" data-switch-button data-day="${esc(row.service_day)}" data-lot="${esc(row.lot_code)}">换版</button>
                        </div>` : (row.locked ? '<small class="lock-note">锁定日不可换版</small>' : '<small>无需换版</small>')}</td>` : ''}
                </tr>`;
            }).join('') || `<tr><td colspan="6">${empty('该场站暂没有已发布预测覆盖的运营日')}</td></tr>`}</tbody>
        </table>
        </div>
        <p class="microcopy">换版请求带唯一 request_id，回执丢失后同号重试不会重复换版；处理结果可在审计事件中追溯。</p>
        <span class="form-status" data-version-status role="status"></span>
    </section>`;
}

export function bindVersionPanel(rerender) {
    const status = document.querySelector('[data-version-status]');
    document.querySelectorAll('[data-switch-button]').forEach(button => {
        button.addEventListener('click', async () => {
            const day = button.dataset.day;
            const lotCode = button.dataset.lot;
            const select = [...document.querySelectorAll('[data-switch-select]')]
                .find(el => el.dataset.day === day && el.dataset.lot === lotCode);
            const forecastCode = select?.value;
            if (!forecastCode) return;
            button.disabled = true;
            if (status) { status.className = 'form-status'; status.textContent = '正在提交换版…'; }
            try {
                const result = await api('/forecasts/versions/switch', {
                    method: 'POST',
                    body: {
                        request_id: makeRequestId(),
                        lot_code: lotCode,
                        service_day: day,
                        forecast_code: forecastCode,
                        note: `预测工作台逐日换版：${day} 切换至 ${forecastCode}`,
                    },
                });
                if (status) {
                    status.className = 'form-status';
                    status.textContent = `${day} 已换版到 ${result.forecast_code}${result.idempotent_replay ? '（幂等重放）' : ''}`;
                }
                await rerender();
            } catch (error) {
                if (status) { status.className = 'form-status error'; status.textContent = error.message; }
                button.disabled = false;
            }
        });
    });
}
