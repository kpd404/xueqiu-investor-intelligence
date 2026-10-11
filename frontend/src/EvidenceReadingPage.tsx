import { useEffect, useState } from "react";
import { ApiError, getEvidenceReading } from "./api";
import type { EvidenceReading, EvidenceOpinion, EvidenceRaw } from "./types";
import { directionLabel, formatEnum, formatTime } from "./presentation";

export function safeSourceUrl(value: string | null): string | null {
  if (!value || /[\u0000-\u0020]/.test(value)) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? value : null;
  } catch { return null; }
}

export function EvidenceReadingPage({assetId, query}: {assetId: string; query: string}) {
  const [view, setView] = useState<EvidenceReading | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setView(null); setError(null);
    getEvidenceReading(assetId, query).then(result => { if (active) setView(result); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason : new Error("证据读取失败")); });
    return () => { active = false; };
  }, [assetId, query, revision]);
  useEffect(() => {
    const recheck = () => setRevision(value => value + 1);
    window.addEventListener("focus", recheck);
    return () => window.removeEventListener("focus", recheck);
  }, []);
  return <div className="asset-product-page evidence-reading-page">
    <header className="product-section">
      <button type="button" onClick={() => window.history.back()}>返回上一页</button>{" "}
      <a href={`/assets/${assetId}`}>返回标的</a>
      <h1>观点与来源证据</h1>
      <button type="button" onClick={() => setRevision(value => value + 1)}>重新校验来源</button>
      <p>原文事实、AI 提取与系统分类分别呈现。历史完整性 UNKNOWN；缺失字段不代表删除、减弱或反转。</p>
    </header>
    {view && <a href={`/research-candidates/new?asset_id=${assetId}&${query.replace(/^\?/, '')}`}>加入研究候选（手动选择）</a>}
    {error ? <section className="product-section" role="alert">
      <h2>{error instanceof ApiError && error.status === 409 ? "指定证据已不可作为当前依据" : "证据读取失败"}</h2>
      <p>{error.message}</p><p>未静默替换来源。返回情报页确认当前状态，或重新校验。</p>
    </section> : !view ? <p role="status">正在校验并读取已保存证据…</p> : <EvidenceContent view={view} />}
  </div>;
}

export function EvidenceContent({view}: {view:EvidenceReading}) {
  const assetId=view.asset.asset_id;
  return <>
      <h2>{view.asset.name} · {view.asset.market}:{view.asset.symbol}</h2>
      {!!view.available_history.length && <details><summary>有效观点历史（非情报关联）</summary>
        {view.available_history.map(record => <p key={record.thesis_change_id}><a href={`/assets/${assetId}/evidence?thesis_change_id=${record.thesis_change_id}`}>{formatEnum(record.change_type)} · {formatTime(record.effective_time)} · 阅读观点与比较</a></p>)}
      </details>}
      {!view.groups.length && <p>当前没有可读取的有效情报关联。历史引用不能补足当前证据。</p>}
      {view.groups.map((group, index) => <section className="product-section" key={`${group.source_id}:${index}`}>
        <h2>{group.basis === "HISTORICAL_REFERENCE" ? "历史上下文（未认证为当前有效）" : group.basis === "EFFECTIVE_HISTORY" ? "当前有效观点历史（不是情报关联）" : "当前有效情报关联"}</h2>
        <p>来源事实时间 {formatTime(group.observed_at)} · <code>{group.source_id}</code></p>
        {group.source_window_start && <p>此来源窗口 {formatTime(group.source_window_start)} — {formatTime(group.source_window_end)}；截止 {formatTime(group.source_as_of)}。仅观察多人观点方向，不证明相同逻辑或共识变化，不与其他窗口拼接。</p>}
        {group.comparison && <div>
          <h3>已有结构化比较 / 系统分类：{formatEnum(group.comparison.change_type)}</h3>
          {group.comparison.change_type === "NEW_THESIS" && <p>当前可用历史中的首次观察；没有前驱不表示投资者此前没有观点。</p>}
          <p>{group.comparison.summary || "未提供比较说明"}</p>
          <ul>{group.comparison.evidence.map((line, i) => <li key={i}>{line}</li>)}</ul>
          <p>比较 confidence {group.comparison.confidence} · policy {group.comparison.comparison_version} · Opinion identity {group.comparison.opinion_analysis_version}</p>
        </div>}
        <div className="evidence-opinion-grid">
          {group.opinions.map(opinion => <OpinionCard key={opinion.opinion_id} opinion={opinion} />)}
        </div>
        {!!group.attention.length && <details><summary>关注贡献原文（仅关注者不作为方向投票者）</summary>
          {group.attention.map(item => <section key={item.attention_occurrence_id}>
            <h3>{group.source_type === "AttentionOccurrence" ? "关注来源（非多人方向投票）" : item.attention_only ? "仅关注贡献" : "方向投票者的关注记录"}</h3><RawCard raw={item.raw} />
          </section>)}
        </details>}
      </section>)}
    </>;
}

function OpinionCard({opinion}: {opinion: EvidenceOpinion}) {
  const role = {THESIS_PREVIOUS: "变化前观点", THESIS_CURRENT: "变化后 / 当前观点", DIRECTION_VOTE: "方向投票观点", ATTENTION_OPINION: "关注来源中的观点（非方向投票）"}[opinion.role];
  return <article className="evidence-opinion-card">
    <h3>{role} · {opinion.raw.investor_name}</h3>
    <p>{formatTime(opinion.raw.published_time)} · {directionLabel(opinion.direction)}</p>
    <h4>AI 提取（不是原始事实）</h4>
    <Field title="投资论点" values={opinion.thesis} />
    <Field title="催化剂" values={opinion.catalysts} />
    <Field title="风险" values={opinion.risks} />
    <p>时间范围：{opinion.time_horizon || "未知 / 未提取"}</p>
    <p>AI confidence：{opinion.confidence}（不代表结论确定性） · 模型 {opinion.model_version}</p>
    <p>Analysis policy：{opinion.analysis_version || "未知"} · Opinion <code>{opinion.opinion_id}</code></p>
    <RawCard raw={opinion.raw} />
  </article>;
}

function Field({title, values}: {title: string; values: string[]}) {
  return <div><h4>{title}</h4>{values.length ? <ul>{values.map((value, i) => <li key={i}>{value}</li>)}</ul> : <p>未提取 / 未知</p>}</div>;
}

function RawCard({raw}: {raw: EvidenceRaw}) {
  const url = safeSourceUrl(raw.source_url);
  return <section className="evidence-raw">
    <h4>原文事实 · {raw.investor_name} · {formatTime(raw.published_time)}</h4>
    <p>RawEvent <code>{raw.raw_event_id}</code> · 来源 {raw.source}</p>
    {raw.contains_repost && <><h4>本作者自述（与引用 / 转发分开）</h4><pre>{raw.current_author_text || "未保存作者自述"}</pre></>}
    <details><summary>展开完整已保存原文（不代表远端全文完整性）</summary>
      <pre>{raw.readable_content}</pre>
      <details><summary>查看原始文本（HTML 以文本显示）</summary><pre>{raw.content}</pre></details>
      <p>引用及转发内容不自动归属为本作者观点；页面不执行原文 HTML。</p>
    </details>
    {url ? <a href={url} target="_blank" rel="noopener noreferrer">打开原帖</a> : <p>原帖链接缺失或不安全，未生成替代链接。</p>}
  </section>;
}
