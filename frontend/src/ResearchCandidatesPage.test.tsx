import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ResearchCandidatesPage } from './ResearchCandidatesPage';
import type { ResearchRecord } from './researchApi';
const row:ResearchRecord={id:'r',asset_id:'a',asset_name:'隔离标的',status:'TODO',reason:'用户原因',questions:'用户问题',notes:'用户笔记',created_at:'2026-10-10T00:00:00Z',updated_at:'2026-10-10T00:00:00Z',references:[],sources:[]};
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();});
it('edits explicit user questions, starts research and keeps saved content after remount',async()=>{
 let saved={...row};
 const fetch=vi.fn().mockImplementation(async(_url:string,options:{method:string;body?:string})=>{
   if(options.method==='PATCH')saved={...saved,...JSON.parse(options.body!)};
   return {ok:true,json:async()=>saved};
 });vi.stubGlobal('fetch',fetch);
 const page=render(<ResearchCandidatesPage id="r" query=""/>);
 await screen.findByDisplayValue('用户问题');fireEvent.change(screen.getByLabelText('待验证问题'),{target:{value:'核验具体事实'}});
 fireEvent.click(screen.getByRole('button',{name:'保存研究内容'}));await screen.findByText('用户研究内容已保存。');
 fireEvent.click(screen.getByRole('button',{name:'开始研究'}));await screen.findByText(/状态：研究中/);
 page.unmount();render(<ResearchCandidatesPage id="r" query=""/>);await screen.findByDisplayValue('核验具体事实');
 expect(saved.status).toBe('RESEARCHING');expect(saved.notes).toBe('用户笔记');
});
it('lists archived record and exposes explicit restore without automatic mutation',async()=>{
 const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({...row,status:'ARCHIVED'})});vi.stubGlobal('fetch',fetch);
 render(<ResearchCandidatesPage id="r" query=""/>);await screen.findByRole('button',{name:'明确恢复为待研究'});
 expect(fetch.mock.calls.every(c=>c[1].method==='GET')).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'明确恢复为待研究'}));await waitFor(()=>expect(fetch.mock.calls.some(c=>c[1].method==='PATCH')).toBe(true));
});
it('source error prevents saving, rather than inventing empty valid evidence',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:409,json:async()=>({detail:'来源已失效'})}));
 render(<ResearchCandidatesPage id={null} query="?asset_id=a&feed_id=f"/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('来源已失效');expect(screen.queryByRole('button',{name:'保存研究候选'})).toBeNull();
});
