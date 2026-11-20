export const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const stamp=v=>v?String(v).replace('T',' ').slice(0,16):'尚未登记';
export const minute=v=>`${String(Math.floor(v/60)).padStart(2,'0')}:${String(v%60).padStart(2,'0')}`;
export const toMinute=s=>s.split(':').map(Number).reduce((a,v,i)=>a+v*(i?1:60),0);
export const fields=form=>Object.fromEntries(new FormData(form));
export function toast(message,error=false){const el=document.querySelector('#toast');el.textContent=message;el.className=error?'show error':'show';clearTimeout(window.quietToast);window.quietToast=setTimeout(()=>el.className='',7000)}
export function download(name,data){const u=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download=name;a.click();URL.revokeObjectURL(u)}
