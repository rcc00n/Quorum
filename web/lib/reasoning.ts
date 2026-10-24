// Types of the upstream 1.0 consumer boundary; canonical owner: ARCHITECTURE.md §8.
export type ReasoningSource = {
  title: string;
  url: string;
  quote?: string | null;
  quote_id?: string | number | null;
};
export type ReasoningEvidence = ReasoningSource & {
  stance: "supports" | "contradicts" | "neutral" | "statement";
  quote: string;
  independence_group: string;
  found_by?: "researcher" | "verifier" | "fact_checker";
  is_document?: boolean;
  by_headline?: boolean;
  source_id?: string | null;
  document_id?: number | null;
  official_doc_id?: number | null;
  char_start?: number | null;
  char_end?: number | null;
  content_hash_at_quote?: string | null;
  access_achieved?: 1 | 2 | null;
  fetched_at?: string | null;
  hash_mismatch?: boolean | null;
  from_previous_day?: boolean;
};
export type ReasoningClaim = {
  id: string;
  text: string;
  kind?: "fact" | "statement" | "number" | "context";
  speaker?: string | null;
  status: "confirmed" | "disputed" | "unverified";
  verifier: "confirmed" | "disputed" | "unverified";
  fact_checker: "confirmed" | "disputed" | "unverified";
  reason: string;
  reviewer_status?: "confirmed" | "disputed" | "unverified" | null;
  reviewer_reason?: string;
  reviewer_quote?: string;
  resolved_by?: "agreement" | "reviewer" | "dispute";
  evidence: ReasoningEvidence[];
};
export type ReasoningStep = {
  node: string;
  iteration: number;
  event_id: string | null;
  decision: string;
  reason: string;
  model: string | null;
  duration_ms: number;
  detail?: { text: string; reason: string }[];
};
export type ReasoningStory = {
  event_id: string;
  rank: number;
  headline: string;
  standfirst: string;
  reading_minutes: number;
  rubric: {
    legal_force: number;
    reach: number;
    irreversibility: number;
    confirmation: number;
    total: number;
    rationale: Partial<
      Record<
        "legal_force" | "reach" | "irreversibility" | "confirmation",
        string
      >
    >;
  };
  photo: {
    url: string;
    credit: string;
    license: string;
    caption: string;
    source_url?: string;
    license_url?: string;
  } | null;
  article: {
    kind: "fact" | "context" | "statements" | "not_confirmed";
    text: string;
    claim_ids: string[];
    sources: ReasoningSource[];
  }[];
  claims: ReasoningClaim[];
  spectrum: {
    rating_mode: "average" | "allsides" | "mbfc" | "adfontes";
    left?: {
      highlights: string;
      omits: string;
      wording: string;
      example_url: string;
    };
    right?: {
      highlights: string;
      omits: string;
      wording: string;
      example_url: string;
    };
    note?: string;
    coverage: Partial<
      Record<
        "major_left" | "minor_left" | "major_right" | "minor_right" | "center",
        [number, number]
      >
    >;
    interpretations: { label: string; outlets: number; mostly: string }[];
    outlets?: {
      source: string;
      cohort: string;
      flank: string;
      url: string;
      highlights: string;
      omits: string;
      wording: string;
      interpretation_label: string;
    }[];
  };
  sources?: ReasoningSource[];
  needs_review: boolean;
  review_reason?: string | null;
  critic_notes?: string | null;
  drafts?: number;
  trace_ref: string;
};
export type ReasoningRoundup = {
  empty_day: boolean;
  count: number;
  groups: {
    name: string;
    items: {
      event_id: string;
      line: string;
      status: string;
      needs_review?: boolean;
      line_source?: "model" | "title";
      sources: ReasoningSource[];
    }[];
  }[];
};
export type ReasoningRun = {
  schema_version: "1.0";
  topic_id: string;
  edition_date: string;
  run_id: string;
  version: number;
  status: "ok" | "partial" | "empty";
  generated_at: string;
  published_at: string | null;
  expires_at: string;
  edition_timezone: string;
  window: { start: string; end: string };
  provenance: {
    corpus: string;
    model: string;
    fictional: boolean;
    fact_checker_model?: string;
    model_calls?: number;
    answered_by?: Record<string, number>;
    model_errors?: number;
  };
  bar?: { threshold: number; confirmation_min: number };
  summary: string;
  summary_source?: "model" | "fallback";
  sources_missing: string[];
  stories: ReasoningStory[];
  roundup: ReasoningRoundup;
  errors?: (
    string | { node: string; event_id: string | null; message: string }
  )[];
  trace?: ReasoningStep[];
};
export type ReasoningPreview = {
  schema_version: "1.0";
  status: "available" | "partial";
  published: false;
  expiry_hint: "expired" | "within_hint";
  sha256: string;
  corpus_binding?: { provisional: boolean; corpus_as_of_utc: string; sidecar_sha256: string };
  missing_provenance: string[];
  warnings: string[];
};
