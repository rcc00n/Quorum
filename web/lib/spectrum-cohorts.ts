// Registry cohort shares (docs/DECISIONS.md › Spectrum ratings and cohorts): four cohorts, major/minor tier
// (registry `tier`) × left/right (the selected mode's score at the agreed ±0.25 thresholds). Pure arithmetic on
// values the caller already computed with lib/api's rating(); no formula is repeated here.
// DECISION(2026-10-27, Anastasia/Claude Code; WEB-SPECTRUM-POLISH-02, prepared for Vadim's data-presentation
// review; amended on his review of PR #52): denominators are stated, never implied. Outlet shares divide by the
// tiered sources rated under the mode (the four cohorts plus tiered sources in the centre); audience shares are
// shares of the supplied cited estimates of those same sources, summed as supplied (not deduplicated reach, not
// unique people), and a source without a cited estimate is counted apart, never as zero. A cohort with members
// but no cited estimate at all has no audience share (null), so an unknown never reads as zero; an empty cohort
// and a cohort whose only cited estimate is zero both read 0. Sources without a tier (agencies, official bodies,
// the centre paper) and sources unrated under the mode are reported as their own buckets. These are registry
// shares; nothing here says which sources covered an event or how many people it reached.
export type CohortInput = { id: string; tier: "major" | "minor" | null | undefined; score: number | null; audience: number | null | undefined; audienceCited: boolean };
export type CohortKey = "major-left" | "major-right" | "minor-left" | "minor-right";
export type CohortRow = { key: CohortKey; tier: "major" | "minor"; lean: "left" | "right"; outlets: number; outletShare: number | null; audience: number; audienceShare: number | null; withoutAudience: number };
export type CohortShares = { rows: CohortRow[]; tiered: number; centre: number; noTier: number; unrated: number; audienceDenominator: number; withAudience: number; withoutAudience: number };
const lean = (score: number) => (score <= -0.25 ? "left" : score >= 0.25 ? "right" : "centre");
const cited = (s: CohortInput) => s.audienceCited && typeof s.audience === "number" && Number.isFinite(s.audience) && s.audience >= 0;
export function cohortShares(inputs: CohortInput[]): CohortShares {
  const rated = inputs.filter(s => typeof s.score === "number" && Number.isFinite(s.score));
  const unrated = inputs.length - rated.length;
  const tieredRated = rated.filter(s => s.tier === "major" || s.tier === "minor");
  const noTier = rated.length - tieredRated.length;
  const centre = tieredRated.filter(s => lean(s.score as number) === "centre").length;
  const withAudienceSet = tieredRated.filter(cited);
  const audienceDenominator = withAudienceSet.reduce((n, s) => n + (s.audience as number), 0);
  const rows: CohortRow[] = (["major", "minor"] as const).flatMap(tier => (["left", "right"] as const).map(side => {
    const members = tieredRated.filter(s => s.tier === tier && lean(s.score as number) === side);
    const withAudience = members.filter(cited);
    const audience = withAudience.reduce((n, s) => n + (s.audience as number), 0);
    return {
      key: `${tier}-${side}` as CohortKey, tier, lean: side,
      outlets: members.length,
      outletShare: tieredRated.length ? members.length / tieredRated.length : null,
      audience,
      audienceShare: members.length === 0 ? 0 : withAudience.length === 0 ? null : audienceDenominator > 0 ? audience / audienceDenominator : 0,
      withoutAudience: members.length - withAudience.length,
    };
  }));
  return { rows, tiered: tieredRated.length, centre, noTier, unrated, audienceDenominator, withAudience: withAudienceSet.length, withoutAudience: tieredRated.length - withAudienceSet.length };
}
