// Geometry only; ratings and audience eligibility are supplied by the existing source model.
export type SpectrumInput = { id: string; score: number; audience: number };
export function spectrumGeometry(input: SpectrumInput[]) {
  const eligible = input.filter(p => Number.isFinite(p.score) && p.score >= -1 && p.score <= 1 && Number.isFinite(p.audience) && p.audience > 0);
  const logs = eligible.map(p => Math.log10(p.audience));
  const low = eligible.length ? Math.min(...logs) : 0;
  const high = eligible.length ? Math.max(...logs) : 0;
  return {
    points: eligible.map(p => ({ ...p, x: (p.score + 1) * 50, y: high === low ? 50 : 100 - (Math.log10(p.audience) - low) / (high - low) * 100 })),
    ticks: eligible.length ? (high === low ? [{ y: 50, audience: 10 ** low }] : [0, .5, 1].map(t => ({ y: t * 100, audience: 10 ** (high - t * (high - low)) }))) : [],
  };
}
