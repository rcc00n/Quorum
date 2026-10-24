// Portal-owned v1 proposal. Reasoning/transport approval is still required.
export type Verification = {
  status: "confirmed" | "not_confirmed" | "contradicted" | "not_run";
  summary: string | null;
  actor: string | null;
  checked_at: string | null;
};
export type Document = {
  id: string;
  source_id: string;
  title: string;
  url: string;
  content_hash: string;
  revision: string | null;
  published_at: string | null;
  fetched_at: string;
  access_level: 1 | 2 | 3;
  kind: "article" | "official";
  primary: boolean;
};
export type Citation = {
  document_id: string;
  summary: string;
  quote: string | null;
  char_start: number | null;
  char_end: number | null;
  content_hash_at_quote: string | null;
};
export type Claim = {
  id: string;
  text: string;
  status: "established" | "attributed" | "disputed" | "unknown";
  explanation: string;
  attribution: { speaker: string; statement_at: string | null } | null;
  supporting: Citation[];
  contradicting: Citation[];
  primary_verification: Verification;
  independent_verification: Verification;
  disagreement: "none" | "present" | "not_assessed";
  confidence_explanation: string | null;
};
export type Frame = {
  source_id: string;
  document_id: string;
  summary: string;
  emphasized_claim_ids: string[];
  interpretations: string[];
};
export type Trace = {
  id: string;
  timestamp: string;
  action:
    | "collection"
    | "clustering"
    | "claim_extraction"
    | "evidence_search"
    | "zetaris_query"
    | "primary_verification"
    | "independent_verification"
    | "contradiction_detection"
    | "recheck"
    | "conclusion_revision"
    | "publication";
  actor: string | null;
  summary: string;
  evidence_refs: string[];
  outcome: string | null;
  revision: string | null;
};
export type Correction = {
  supersedes_claim_id: string;
  replacement_claim_id: string | null;
  previous_revision: string;
  timestamp: string;
  summary: string;
};
export type StructuredAnalysis = {
  documents: Document[];
  claims: Claim[];
  frames: Frame[];
  trace: Trace[];
  corrections: Correction[];
  coverage: {
    covered_source_ids: string[];
    eligible_source_ids: string[] | null;
    publication_count: number | null;
    independent_confirmation_count: number | null;
  };
};
export type Publication = {
  status: "pending" | "available" | "partial" | "stale" | "error";
  revision?: string;
  edition?: string;
  run_id?: string;
  generated_at?: string;
  expires_at?: string;
  published_at?: string;
  source_revision?: string | null;
  previous_revision?: string | null;
  fallback?: boolean;
  error_code?: string | null;
  mode?: "live" | "demo";
};
export function displayTime(value: string | null | undefined) {
  if (!value) return "Not supplied";
  const d = new Date(value);
  return Number.isNaN(d.valueOf())
    ? "Unavailable"
    : new Intl.DateTimeFormat("en", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "UTC",
      }).format(d) + " UTC";
}
