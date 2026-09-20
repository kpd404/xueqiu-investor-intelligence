import type {
  AssetListResponse,
  AssetIntelligenceView,
  CombinedAssetView,
  InvestorIntelligenceView,
  InvestorProductView,
  InvestorListResponse,
  IntelligenceFeedListResponse,
  OperationalStatusResponse,
  TimelineResponse
} from "./types";

const API_BASE = "/api/v1/intelligence";
const PRODUCT_API_BASE = "/api/intelligence";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" }
  });
  if (!response.ok) {
    let message = "The intelligence API is unavailable.";
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) message = payload.detail;
    } catch {
      // Keep the safe generic error when the server did not return JSON.
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

export function getAssetList(): Promise<AssetListResponse> {
  return request<AssetListResponse>(API_BASE + "/assets?limit=100&offset=0");
}

export function getAsset(assetId: string): Promise<CombinedAssetView> {
  return request<CombinedAssetView>(API_BASE + "/assets/" + encodeURIComponent(assetId));
}

export function getAssetTimeline(assetId: string): Promise<TimelineResponse> {
  return request<TimelineResponse>(
    API_BASE + "/assets/" + encodeURIComponent(assetId) + "/timeline"
  );
}

export function getAssetIntelligenceView(assetId: string): Promise<AssetIntelligenceView> {
  return request<AssetIntelligenceView>(
    PRODUCT_API_BASE + "/assets/" + encodeURIComponent(assetId) + "/view"
  );
}

export function getInvestorList(): Promise<InvestorListResponse> {
  return request<InvestorListResponse>(API_BASE + "/investors");
}

export function getInvestor(investorId: string): Promise<InvestorIntelligenceView> {
  return request<InvestorIntelligenceView>(
    API_BASE + "/investors/" + encodeURIComponent(investorId)
  );
}

export function getInvestorIntelligenceView(investorId: string): Promise<InvestorProductView> {
  return request<InvestorProductView>(
    PRODUCT_API_BASE + "/investors/" + encodeURIComponent(investorId) + "/view"
  );
}

export function getOperationalStatus(): Promise<OperationalStatusResponse> {
  return request<OperationalStatusResponse>("/api/operations/status");
}

export function getRecentIntelligence(
  since: string,
  limit = 20
): Promise<IntelligenceFeedListResponse> {
  return request<IntelligenceFeedListResponse>(
    "/api/intelligence/feed?limit=" +
      limit +
      "&state=ACTIVE&since=" +
      encodeURIComponent(since)
  );
}
