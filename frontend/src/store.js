import {api} from './api.js';
export const store={user:JSON.parse(sessionStorage.getItem('quiet-user')||'null'),cases:[],selected:Number(sessionStorage.getItem('quiet-case')||1),clock:''};
export async function refresh(){[store.cases,{at:store.clock}]=await Promise.all([api('/complaints'),api('/clock')]);if(!store.cases.some(c=>c.id===store.selected))store.selected=store.cases[0]?.id||0}
export function choose(id){store.selected=Number(id);sessionStorage.setItem('quiet-case',id)}
export const currentCase=()=>store.cases.find(c=>c.id===store.selected);
export async function latestAgreement(){return (await api(`/complaints/${store.selected}/agreements`)).find(a=>!['cancelled','fulfilled'].includes(a.state))||(await api(`/complaints/${store.selected}/agreements`))[0]}
