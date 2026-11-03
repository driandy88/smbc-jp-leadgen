export type Term = { jp: string; en: string; hint: string };
export type ScoutConfig = {
  keywords: { groups: { key: string; label: string; terms: Term[] }[]; packs: { key: string; label: string; brief: string; terms: string[] }[] };
  default_mock: boolean;
  res_range: [number, number];
  usd_rate: number;
  currency: string;
  sku: string;
  usd_per_call: number;
  has_maps_key: boolean;
};
export type City = { key: string; jp: string; en: string; pref: string; areas: number; km2: number };
export type Area = { code: string; jp: string; en: string; km2: number; cells: number };
export type AreaRef = { city: string; area: string };

export type Estimate = {
  cells: number; keywords: number; tasks: number; min_calls: number; expected_calls: number; calls_per_task: number;
  basis: "history" | "default"; duration?: { workers: number; latency_s: number; minutes: number; minutes_sequential: number }; expected_usd: number; expected_local: number; min_local: number; usd_per_call: number; sku: string;
  by_res: { res: number; km2: number; cells: number | null }[];
};

export type Run = {
  id: number; status: string; mock: boolean; error: string | null; author: string; created_at: string; finished_at: string | null;
  keywords: string[]; areas: AreaRef[]; base_res: number; max_res: number; total_tasks: number; done_tasks: number;
  raw_hits: number; unique_places: number; dupes: number; saturated: number; splits: number; api_calls: number;
  cost_usd: number; cost_local: number; estimate: Estimate | null;
  logs?: { t: string; level: string; m: string }[];
  area_progress?: { area: string; jp: string; en: string; done: number; total: number }[];
};

export type Filters = {
  status: string[]; minRating: number; unrated: boolean; revIdx: number; days: number[]; from: string; to: string;
  hasHours: boolean; price: number[]; pay: string[]; types: string[]; svc: string[]; qual: string[]; areas: string[]; fnb?: string[];
};

export type Opt = { k: string; l: string; n: number; en?: string };
export type FilterResult = {
  total: number; count: number; funnel: { l: string; n: number; d: number }[]; filters: Filters; defaults: Filters;
  options: {
    status: Opt[]; fnb?: Opt[]; price: (Opt & { k: number })[]; pay: Opt[]; types: Opt[]; svc: Opt[]; qual: Opt[]; areas: Opt[];
    rating_hist: number[]; review_hist: number[]; unrated: number; no_hours: number; review_steps: number[];
  };
  preview: { pk: number; name: string; area: string; type: string; rating: number | null; reviews: number | null; price: string; pay: string; pay_label: string; today: string; maps_uri: string; status: string; phone: string | null; web: string | null }[];
  sort: string;
};

export type Version = {
  id: number; name: string; notes: string; author: string; created_at: string; run_id: number; rows: number; diff: number | null;
  cities: string[]; areas: number; keywords: number; mock: boolean; cost_local: number; export_uri: string | null; analyzed: boolean;
};

// The profile from services/analysis.py; loosely typed on purpose
export type Profile = any;
