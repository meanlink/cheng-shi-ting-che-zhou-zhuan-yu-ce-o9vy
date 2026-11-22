export const windowStatus = {
    proposed: ['待批准', 'watch'],
    approved: ['待开放', 'info'],
    open: ['正在收车', 'good'],
    paused: ['暂停收车', 'watch'],
    ended: ['待交班盘点', 'info'],
    reconciled: ['已结案', 'good'],
    cancelled: ['已撤销', ''],
};

export const closeoutStatus = {
    flagged: ['账实差异', 'critical'],
    ready: ['待主管复核', 'watch'],
    returned: ['已退回', 'critical'],
    accepted: ['已通过', 'good'],
};

const clock = new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit', minute: '2-digit', timeZone: 'UTC', hourCycle: 'h23',
});

export const utcClock = value => clock.format(new Date(value));
export const utcRange = window => `${window.service_day} · ${utcClock(window.starts_at)}–${utcClock(window.ends_at)} UTC`;

export const windowActions = {
    approve: ['批准窗口', '批准后该时段将占用接收场车位配额。'],
    open: ['开放入口', '确认现场已设置分流指引，可以收车。'],
    pause: ['暂停收车', '入口停止收车，闸机仍可登记离场。'],
    resume: ['恢复收车', '恢复前将重新核算接收场余位。'],
    end: ['结束窗口', '全部分流车辆离场后，移交分析员盘点。'],
    cancel: ['撤销窗口', '撤销后释放该窗口的预留车位。'],
};

export function allowedActions(role, status) {
    if (role === 'operator') return {
        approved: ['open'], open: ['end'], paused: ['end'],
    }[status] || [];
    if (role === 'supervisor') return {
        proposed: ['approve', 'cancel'], approved: ['cancel'], open: ['pause'], paused: ['resume'],
    }[status] || [];
    return [];
}
