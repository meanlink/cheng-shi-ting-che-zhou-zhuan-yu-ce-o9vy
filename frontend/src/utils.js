export const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const fmt=(value,digits=0)=>Number(value||0).toLocaleString('zh-CN',{maximumFractionDigits:digits});
export const dateOnly=value=>value?new Date(value).toLocaleDateString('zh-CN',{month:'2-digit',day:'2-digit'}):'—';
export const dateTime=value=>value?new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'—';
