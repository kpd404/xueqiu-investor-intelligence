import {useEffect,useRef,useState} from 'react';
import {RecentIntelligenceCard} from './OverviewPage';
import type {IntelligenceFeedItem} from './types';

type Progress={read:boolean;processed:boolean};
type Item=IntelligenceFeedItem & {user_state:Progress};
type Result={items:Item[];total:number;limit:number;offset:number;has_more:boolean};
type Filter='ALL'|'UNREAD'|'PENDING';
async function api<T>(url:string,body?:Partial<Progress>):Promise<T>{
 const response=await fetch(url,{method:body?'PATCH':'GET',headers:{Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
 if(!response.ok)throw new Error(response.status===404||response.status===503?'用户处理尚未在此环境启用；未保存操作。':'请求失败，未确认保存；请重试或重新读取状态。');
 return response.json();
}
export function InboxPage(){
 const [filter,setFilter]=useState<Filter>(()=>{const value=new URLSearchParams(location.search).get('filter');return value==='UNREAD'||value==='PENDING'?value:'ALL';});
 const [offset,setOffset]=useState(()=>{const value=Number(new URLSearchParams(location.search).get('offset'));return Number.isSafeInteger(value)&&value>=0?value:0;});
 const [result,setResult]=useState<Result|null>(null);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');
 const [message,setMessage]=useState('');
 const [busy,setBusy]=useState<string|null>(null);
 const [revision,setRevision]=useState(0);
 const epoch=useRef(0);
 const [since]=useState(()=>new URLSearchParams(location.search).get('since')??new Date(Date.now()-24*60*60*1000).toISOString());
 useEffect(()=>{const refresh=(event:PageTransitionEvent)=>{if(event.persisted)setRevision(v=>v+1);};window.addEventListener('pageshow',refresh);return()=>window.removeEventListener('pageshow',refresh);},[]);
 useEffect(()=>{
  const params=new URLSearchParams(location.search);params.set('filter',filter);params.set('offset',String(offset));params.set('since',since);history.replaceState(null,'',location.pathname+'?'+params);
  const token=++epoch.current;setLoading(true);setError('');
  api<Result>('/api/inbox?'+new URLSearchParams({filter,offset:String(offset),limit:'20',state:'ACTIVE',since})).then(value=>{if(epoch.current===token)setResult(value);}).catch(e=>{if(epoch.current===token){setError(e.message);setResult(null);}}).finally(()=>{if(epoch.current===token)setLoading(false);});
 },[filter,offset,revision,since]);
 async function save(item:Item,patch:Partial<Progress>){
  setBusy(item.id);setMessage('保存中…');setError('');
  try{await api('/api/inbox/'+item.id+'/user-state',patch);setMessage('用户状态已保存；系统情报生命周期未改变。');setRevision(v=>v+1);}
  catch(e){setMessage('');setError(e instanceof Error?e.message:'未确认保存');}
  finally{setBusy(null);}
 }
 return <section className="overview-section inbox-user-page" aria-label="Inbox 用户处理">
  <a className="inbox-user-link" href="/">返回情报概览</a><h1>Inbox 用户处理</h1>
  <p>阅读与处理进度是用户操作，不改变情报有效性、研究优先级或系统状态。阅读证据和加入研究候选不会自动标记。</p>
  <p className="inbox-user-scope">来源事实时间起点：{since} · 仅当前有效 ACTIVE 情报</p>
  <div className="inbox-user-toolbar" aria-label="用户状态筛选">
   {(['ALL','UNREAD','PENDING'] as Filter[]).map(value=><button key={value} className="inbox-user-button" aria-pressed={filter===value} disabled={busy!==null} onClick={()=>{setFilter(value);setOffset(0);}}>{{ALL:'全部',UNREAD:'未读',PENDING:'待处理'}[value]}</button>)}
  </div>
  {message&&<p role="status">{message}</p>}{error&&<p role="alert">{error}</p>}
  {loading?<p role="status">正在读取有效情报和用户状态…</p>:result&&<>
   <p>符合当前筛选：{result.total} 条</p>
   {result.items.length===0&&<p>当前范围没有符合条件的情报。</p>}
   {result.items.map(item=><div key={item.id} className="inbox-user-entry">
    <RecentIntelligenceCard item={item} onOpenAsset={id=>location.assign('/assets/'+id)} onOpenInvestor={id=>location.assign('/investors/'+id)}/>
    <div className="inbox-user-toolbar"><strong>阅读：{item.user_state.read?'已读':'未读'} · 处理：{item.user_state.processed?'已处理':'待处理'}</strong>
     <button className="inbox-user-button" disabled={busy!==null} onClick={()=>save(item,{read:!item.user_state.read})}>{item.user_state.read?'恢复未读':'明确标记已读'}</button>
     <button className="inbox-user-button" disabled={busy!==null} onClick={()=>save(item,{processed:!item.user_state.processed})}>{item.user_state.processed?'恢复待处理':'明确标记已处理'}</button>
    </div>
   </div>)}
   <div className="inbox-user-toolbar"><button className="inbox-user-button" disabled={offset===0||busy!==null} onClick={()=>setOffset(v=>Math.max(0,v-20))}>上一页</button><span>第 {Math.floor(offset/20)+1} 页</span><button className="inbox-user-button" disabled={!result.has_more||busy!==null} onClick={()=>setOffset(v=>v+20)}>下一页</button></div>
  </>}
 </section>;
}
