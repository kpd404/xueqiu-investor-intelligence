import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { EvidenceReadingPage, safeSourceUrl } from "./EvidenceReadingPage";
import type { EvidenceReading } from "./types";

const content = "<p>作者自述</p>" + "完整长文".repeat(1000) + "//@引用作者：引用内容<script>bad()</script>";
const raw = {raw_event_id: "r", investor_id: "i", investor_name: "真实来源作者", published_time: "2026-10-10T00:00:00Z", source: "xueqiu", source_url: "https://xueqiu.com/123/456", source_url_status: "AVAILABLE", content, readable_content: "完整长文".repeat(1000), current_author_text: "作者自述", contains_repost: true};
const reading: EvidenceReading = {asset: {asset_id:"a", name:"测试标的", market:"SH", symbol:"1"}, historical_completeness:"UNKNOWN", available_history: [], groups: [{source_id:"t", source_type:"ThesisChange", signal_id:"s", event_id:"e", basis:"CURRENT_ASSOCIATION", observed_at:raw.published_time, source_window_start:null, source_window_end:null, source_as_of:null, direction_voter_ids:[], attention_only_investor_ids:[], comparison:{change_type:"THESIS_CHANGED", summary:"已有比较说明", evidence:["已保存比较依据"], confidence:0.6, comparison_version:"approved", opinion_analysis_version:"approved"}, opinions:[{opinion_id:"o", role:"THESIS_CURRENT", direction:"BULLISH", thesis:["提取论点"], catalysts:[], risks:[], time_horizon:null, confidence:0.4, analysis_id:"analysis", analysis_version:"approved", model_version:"model", raw}], attention:[]}]};

afterEach(() => {cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();});

it("reads full saved text with attribution, missing fields, confidence and safe original link", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok:true, json:async()=>reading}));
  render(<EvidenceReadingPage assetId="a" query="?signal_id=s" />);
  await screen.findByText("提取论点");
  expect(screen.getByText(/AI confidence：0.4/)).toBeInTheDocument();
  expect(screen.getAllByText(/未提取/).length).toBeGreaterThan(0);
  fireEvent.click(screen.getByText("展开完整已保存原文（不代表远端全文完整性）"));
  expect(screen.getByText("完整长文".repeat(1000))).toBeInTheDocument();
  expect(document.querySelector("script")).toBeNull();
  expect(screen.getByRole("link", {name:"打开原帖"})).toHaveAttribute("href", raw.source_url);
  expect(screen.getByRole("link", {name:"打开原帖"})).toHaveAttribute("rel", "noopener noreferrer");
  expect(screen.getByText("作者自述")).toBeInTheDocument();
});

it("rechecks a pinned source and clearly stops displaying invalidated content", async () => {
  const fetch = vi.fn().mockResolvedValueOnce({ok:true,json:async()=>reading})
    .mockResolvedValueOnce({ok:false,status:409,json:async()=>({detail:"有效前驱已变化"})});
  vi.stubGlobal("fetch", fetch);
  render(<EvidenceReadingPage assetId="a" query="?signal_id=s" />);
  await screen.findByText("提取论点");
  fireEvent.click(screen.getByRole("button", {name:"重新校验来源"}));
  await screen.findByText("指定证据已不可作为当前依据");
  expect(screen.queryByText("提取论点")).not.toBeInTheDocument();
  await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(2));
  expect(fetch.mock.calls[1][0]).toBe("/api/intelligence/assets/a/evidence?signal_id=s");
});

it("labels first observation and explicit historical context separately and supports return", async () => {
  const fixture = structuredClone(reading);
  fixture.groups[0].basis = "HISTORICAL_REFERENCE";
  fixture.groups[0].comparison!.change_type = "NEW_THESIS";
  fixture.groups[0].opinions[0].raw.source_url = "javascript:bad()";
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok:true,json:async()=>fixture}));
  const back = vi.spyOn(window.history,"back").mockImplementation(()=>undefined);
  render(<EvidenceReadingPage assetId="a" query="?history=true&thesis_change_id=t" />);
  await screen.findByText("历史上下文（未认证为当前有效）");
  expect(screen.getByText(/首次观察；没有前驱不表示/)).toBeInTheDocument();
  expect(screen.queryByRole("link", {name:"打开原帖"})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name:"返回上一页"}));
  expect(back).toHaveBeenCalledOnce();
});

it("rejects missing, unsafe and credential-bearing source URLs", () => {
  for (const url of [null,"javascript:x()","data:text/html,x","//xueqiu.com/1","https://u:secret@xueqiu.com","https://xueqiu.com/\n1"]) expect(safeSourceUrl(url)).toBeNull();
});
