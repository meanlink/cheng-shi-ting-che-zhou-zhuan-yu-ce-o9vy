import {empty} from '../components.js';
import {esc} from '../utils.js';

export function requestForm(forecasts, lots) {
    const published = forecasts.filter(row => row.status === 'published');
    if (!published.length) return empty('先在预测工作台发布覆盖目标运营日的预测。');
    return `<form class="stack" data-overflow-form="window">
        <label>窗口编号<input name="reference" minlength="3" maxlength="48" required placeholder="OF-AM-07"></label>
        <label>已发布预测<select name="forecast_code" required><option value="">选择来源场站预测</option>
            ${published.map(row => `<option value="${esc(row.code)}" data-source="${esc(row.lot_code)}">
                ${esc(row.code)} · ${esc(row.lot_name)}</option>`).join('')}</select></label>
        <label>接收停车场<select name="target_lot_code" required><option value="">选择停车场</option>
            ${lots.filter(lot => lot.status === 'active').map(lot => `<option value="${esc(lot.code)}">${esc(lot.name)}</option>`).join('')}
        </select></label>
        <div class="overflow-fields">
            <label>开始时间 · UTC<input type="datetime-local" name="starts_at" required></label>
            <label>结束时间 · UTC<input type="datetime-local" name="ends_at" required></label>
        </div>
        <label>溢流车位配额<input name="bay_limit" type="number" min="1" max="10000" required></label>
        <label>调度说明<textarea name="reason" rows="2" minlength="4" maxlength="240" required></textarea></label>
        <div class="form-status" role="status"></div><button class="button">提交窗口</button>
    </form>`;
}

export function bindForecastTarget(form) {
    if (!form) return;
    function filterTarget() {
        const source = form.elements.forecast_code.selectedOptions[0]?.dataset.source;
        const target = form.elements.target_lot_code;
        for (const option of target.options) option.disabled = Boolean(source && option.value === source);
        if (target.selectedOptions[0]?.disabled) target.value = '';
    }
    form.elements.forecast_code.addEventListener('change', filterTarget);
    filterTarget();
}
