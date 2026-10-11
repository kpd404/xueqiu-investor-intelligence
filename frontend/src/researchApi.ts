import { ApiError } from './api';
import type { EvidenceReading } from './types';
export type ResearchStatus = 'TODO' | 'RESEARCHING' | 'ARCHIVED';
export interface ResearchReference { feed_id:string|null;event_id:string|null;signal_id:string|null;source_type:string;source_id:string;opinion_ids:string[];raw_event_ids:string[]; }
export interface ResearchRecord {
  id:string;asset_id:string;asset_name:string;status:ResearchStatus;reason:string;questions:string;notes:string;
  created_at:string;updated_at:string;references:ResearchReference[];
  sources?:{status:string;message:string;evidence:EvidenceReading|null}[];
}
async function request<T>(path:string,method='GET',body?:unknown):Promise<T> {
  const r=await fetch('/api/research-candidates'+path,{method,headers:{Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
  if(!r.ok){let message='研究记录请求失败；未确认保存。';try{const d=await r.json();if(typeof d.detail==='string')message=d.detail;}catch{/* retain safe message */}throw new ApiError(r.status,message);}
  return r.json();
}
export const listResearch=()=>request<{items:ResearchRecord[]}>('');
export const readResearch=(id:string)=>request<ResearchRecord>('/'+encodeURIComponent(id));
export const addResearch=(body:unknown)=>request<ResearchRecord>('','POST',body);
export const editResearch=(id:string,body:Partial<Pick<ResearchRecord,'reason'|'questions'|'notes'|'status'>>)=>request<ResearchRecord>('/'+encodeURIComponent(id),'PATCH',body);
export const researchLabels:Record<ResearchStatus,string>={TODO:'待研究',RESEARCHING:'研究中',ARCHIVED:'已归档'};
