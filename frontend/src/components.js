import {esc} from './utils.js';
export function badge(label,tone=''){return `<span class="badge ${tone}">${esc(label)}</span>`;}
export function stat(label,value,detail=''){return `<div class="stat"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(detail)}</small></div>`;}
export function empty(text){return `<div class="empty">${esc(text)}</div>`;}
