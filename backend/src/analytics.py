from datetime import date, timedelta
from statistics import mean

def _daily_series(rows):
    grouped = {}
    for row in rows:
        key = row['observed_at'].date(); grouped[key] = grouped.get(key, 0) + row['entry_count'] + row['exit_count']
    return sorted(grouped.items())

def seasonal_moving_average(rows, start: date, horizon_days: int):
    series = _daily_series(rows)
    if not series: raise ValueError('没有可用于预测的时段观测')
    recent_values = [v for _, v in series[-7:]]; predictions = []
    for offset in range(horizon_days):
        target = start + timedelta(days=offset)
        same_weekday = [v for day, v in series if day.weekday() == target.weekday()][-4:]
        value = round(mean(same_weekday or recent_values), 2)
        predictions.append({'date': target.isoformat(), 'weekday': target.strftime('%a'), 'turnover': value})
    return predictions

def rolling_backtest(rows):
    series = _daily_series(rows)
    if len(series) < 8: raise ValueError('至少需要 8 个完整日历日才能滚动回测')
    absolute = []; percentage = []
    for index in range(7, len(series)):
        history = series[:index]; target_day, actual = series[index]
        same_weekday = [v for day, v in history if day.weekday() == target_day.weekday()][-4:]
        estimate = mean(same_weekday or [v for _, v in history[-7:]])
        absolute.append(abs(actual - estimate))
        if actual: percentage.append(abs(actual-estimate) / actual * 100)
    return round(mean(absolute), 2), round(mean(percentage), 4)

def calendar_complete(rows, anchor: date):
    dates = {r['observed_at'].date() for r in rows}
    return {anchor - timedelta(days=i) for i in range(1, 8)}.issubset(dates)
