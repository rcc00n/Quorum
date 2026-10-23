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
};
export type ReasoningClaim = {
  id: string;
  text: string;
  kind?: "fact" | "statement" | "number";
  speaker?: string | null;
  status: "confirmed" | "disputed" | "unverified";
  verifier: "confirmed" | "disputed" | "unverified";
  fact_checker: "confirmed" | "disputed" | "unverified";
  reason: string;
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
    left: {
      highlights: string;
      omits: string;
      wording: string;
      example_url: string;
    };
    right: {
      highlights: string;
      omits: string;
      wording: string;
      example_url: string;
    };
    note: string;
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
  bar?: { threshold: number; confirmation_min: number };
  summary: string;
  sources_missing: string[];
  stories: ReasoningStory[];
  roundup: ReasoningRoundup;
  errors?: string[];
  trace?: ReasoningStep[];
};
export type ReasoningPreview = {
  schema_version: "1.0";
  status: "available" | "partial";
  published: false;
  sha256: string;
  missing_provenance: string[];
  warnings: string[];
};
