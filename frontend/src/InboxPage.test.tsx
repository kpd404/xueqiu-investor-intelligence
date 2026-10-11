import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {InboxPage} from './InboxPage';
const item={id:'feed',asset:{asset_id:'asset',name:'隔离标的',market:'SH',symbol:'1'},title:'观察到投资逻辑变化',reason:'THESIS_CHANGE_OBSERVED',priority_level:'MEDIUM',state:'ACTIVE',event_type:'INVESTOR_VIEW_CHANGE',context:{signal_count:1},investors:[],observed_at:'2026-10-10T00:00:00Z',created_at:'2026-10-10T00:00:00Z',user_state:{read:false,processed:false}};
afterEach(()=>{cleanup();history.replaceState(null,'','/');vi.unstubAllGlobals();vi.restoreAllMocks();});
it('only explicit clicks write, keeps source links and reports successful progress',async()=>{
 let state={...item.user_state};
 const fetch=vi.fn(async(url:string,opts:{method:string;body?:string})=>{
  if(opts.method==='PATCH'){state={...state,...JSON.parse(opts.body!)};return {ok:true,json:async()=>state};}
  const pending=!url.includes('filter=UNREAD')||!state.read;
  return {ok:true,json:async()=>({items:pending?[{...item,user_state:state}]:[],total:pending?1:0,limit:20,offset:0,has_more:false})};
 });vi.stubGlobal('fetch',fetch);render(<InboxPage/>);
 await screen.findByText('阅读：未读 · 处理：待处理');
 expect(fetch.mock.calls.every(c=>c[1].method==='GET')).toBe(true);
 expect(screen.getByRole('link',{name:'查看证据'})).toHaveAttribute('href','/assets/asset/evidence?feed_id=feed');
 fireEvent.click(screen.getByRole('button',{name:'明确标记已读'}));
 await screen.findByText('阅读：已读 · 处理：待处理');
 fireEvent.click(screen.getByRole('button',{name:/^未读$/}));
 await screen.findByText('符合当前筛选：0 条');
 expect(state.processed).toBe(false);
});
it('failed save does not show saved or flip the state',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(_url:string,opts:{method:string})=>opts.method==='PATCH'?{ok:false,status:500}:{ok:true,json:async()=>({items:[item],total:1,limit:20,offset:0,has_more:false})}));
 render(<InboxPage/>);await screen.findByText('阅读：未读 · 处理：待处理');
 fireEvent.click(screen.getByRole('button',{name:'明确标记已处理'}));
 await screen.findByRole('alert');expect(screen.getByText('阅读：未读 · 处理：待处理')).toBeInTheDocument();
 expect(screen.queryByText('用户状态已保存；系统情报生命周期未改变。')).toBeNull();
});
it('restores filter on return and reloads persisted page state without writing',async()=>{
 history.replaceState(null,'','/inbox?filter=PENDING&offset=20&since=2026-09-01T00%3A00%3A00Z');
 const fetch=vi.fn(async(_url:string,_opts:unknown)=>({ok:true,json:async()=>({items:[item],total:21,limit:20,offset:20,has_more:false})}));vi.stubGlobal('fetch',fetch);
 render(<InboxPage/>);await screen.findByText('阅读：未读 · 处理：待处理');
 expect(screen.getByRole('button',{name:/^待处理$/})).toHaveAttribute('aria-pressed','true');
 expect(screen.getByText('第 2 页')).toBeInTheDocument();
 const before=fetch.mock.calls.length;
 fireEvent(window,new PageTransitionEvent('pageshow',{persisted:true}));
 await waitFor(()=>expect(fetch.mock.calls.length).toBeGreaterThan(before));
 expect(fetch.mock.calls.every(c=>String(c[0]).includes('filter=PENDING'))).toBe(true);
});
