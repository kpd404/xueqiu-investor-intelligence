import { useEffect, useState } from 'react';
import { getEvidenceReading } from './api';
import { EvidenceContent } from './EvidenceReadingPage';
import { addResearch, editResearch, listResearch, readResearch, researchLabels } from './researchApi';
import type { ResearchRecord, ResearchStatus } from './researchApi';
import type { EvidenceReading } from './types';

export function ResearchCandidatesPage({id,query}:{id:string|null;query:string}) {
  const params=new URLSearchParams(query),asset=params.get('asset_id');
  const [items,setItems]=useState<ResearchRecord[]>([]),[record,setRecord]=useState<ResearchRecord|null>(null);
  const [evidence,setEvidence]=useState<EvidenceReading|null>(null),[selected,setSelected]=useState<number[]>([]);
  const [reason,setReason]=useState(''),[questions,setQuestions]=useState(''),[notes,setNotes]=useState('');
  const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
  const [submission]=useState(()=>crypto.randomUUID());
  useEffect(()=>{let active=true;setError('');setRecord(null);setEvidence(null);
    const load=async()=>{if(id){const row=await readResearch(id);if(!active)return;setRecord(row);setReason(row.reason);setQuestions(row.questions);setNotes(row.notes);}
      else if(asset){const selectors=new URLSearchParams(query);selectors.delete('asset_id');const view=await getEvidenceReading(asset,'?'+selectors.toString());if(!active)return;setEvidence(view);setSelected(view.groups.map((_,i)=>i));}
      else {const result=await listResearch();if(active)setItems(result.items);}};
    load().catch(e=>{if(active)setError(e.message);});return()=>{active=false;};
  },[id,query]);
  const save=async()=>{setBusy(true);setError('');setNotice('');try{
    if(id){await editResearch(id,{reason,questions,notes});setRecord(await readResearch(id));setNotice('用户研究内容已保存。');}
    else if(asset && evidence){const row=await addResearch({asset_id:asset,submission_id:submission,feed_id:params.get('feed_id'),reason,questions,notes,
      selections:selected.map(i=>{const g=evidence.groups[i];return g.signal_id?{event_id:g.event_id,signal_id:g.signal_id}:{thesis_change_id:g.source_id};})});window.location.assign('/research-candidates/'+row.id);}
  }catch(e){setError(e instanceof Error?e.message:'保存失败');}finally{setBusy(false);}};
  const changeStatus=async(value:ResearchStatus)=>{if(!id)return;setBusy(true);setError('');try{await editResearch(id,{status:value});setRecord(await readResearch(id));setNotice('用户状态已更新；不改变系统 Feed 状态。');}catch(e){setError(e instanceof Error?e.message:'更新失败');}finally{setBusy(false);}};
  return <div className="asset-product-page research-page">
    <header className="product-section"><a href="/research-candidates">研究候选列表</a><h1>研究候选</h1><p>用户主动选择继续研究，不表示买卖建议、收益预测或投资结论。用户记录与原文、AI 提取分开。</p></header>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {!id && !asset && <section className="product-section">{!items.length && <p>尚未保存研究候选。阅读情报或证据后手动加入。</p>}{items.map(row=><article key={row.id}><a href={'/research-candidates/'+row.id}>{row.asset_name}</a> · {researchLabels[row.status]}<p>{row.reason||'未填写用户研究原因'}</p></article>)}</section>}
    {(record || evidence) && <section className="product-section"><h2>{record?.asset_name||evidence?.asset.name}</h2>
      {record && <><p>状态：{researchLabels[record.status]} · 创建：{record.created_at}</p><button disabled={busy||record.status==='TODO'} onClick={()=>changeStatus('TODO')}>{record.status==='ARCHIVED'?'明确恢复为待研究':'设为待研究'}</button>{' '}<button disabled={busy||record.status==='RESEARCHING'} onClick={()=>changeStatus('RESEARCHING')}>{record.status==='ARCHIVED'?'明确恢复为研究中':'开始研究'}</button>{' '}<button disabled={busy||record.status==='ARCHIVED'} onClick={()=>changeStatus('ARCHIVED')}>归档候选</button></>}
      <h3>用户判断与研究记录</h3>
      <label>研究原因<textarea value={reason} onChange={e=>setReason(e.target.value)} maxLength={20000}/></label>
      <label>待验证问题<textarea value={questions} onChange={e=>setQuestions(e.target.value)} maxLength={20000}/></label>
      <label>用户笔记<textarea value={notes} onChange={e=>setNotes(e.target.value)} maxLength={50000}/></label>
      {evidence && <fieldset><legend>手动选择具体证据引用</legend>{evidence.groups.map((g,i)=><label key={g.source_id+':'+i}><input type="checkbox" checked={selected.includes(i)} onChange={e=>setSelected(old=>e.target.checked?[...old,i]:old.filter(n=>n!==i))}/>{g.source_type} · {g.observed_at} · {g.source_id}</label>)}</fieldset>}
      <button disabled={busy||(!record&&!selected.length)} onClick={save}>{busy?'正在保存…':record?'保存研究内容':'保存研究候选'}</button>
      {!record && <p>同标的已有未归档记录时复用并补充引用，不覆盖已有原因、问题或笔记。请在详情页明确编辑。</p>}
    </section>}
    {record?.sources?.map((source,i)=>{const ref=record.references[i];const selectors=ref.signal_id?`event_id=${ref.event_id}&signal_id=${ref.signal_id}`:`thesis_change_id=${ref.source_id}`;return <section className="product-section" key={i}>
      <h2>保存的来源引用 {i+1} · {source.status==='CURRENT'?'当前有效':source.status==='HISTORICAL'?'历史上下文':'尚未验证 / 缺失'}</h2><p>{source.message}</p>
      <a href={`/assets/${record.asset_id}/evidence?${selectors}${ref.feed_id?'&feed_id='+ref.feed_id:''}`}>返回来源证据（重新校验当前状态）</a>
      <p>外部原帖曾只验证正确地址和标题，远端正文读取超时；外部不可访问不代表本地已保存原文缺失。</p>
      {source.evidence && <EvidenceContent view={source.evidence}/>}</section>;})}
  </div>;
}
