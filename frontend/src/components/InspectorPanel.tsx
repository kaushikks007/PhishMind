import type { ScanResult } from '../types';
import { cn } from '../lib/utils';

function verdictBg(verdict: string) {
  if (verdict === 'PHISHING') return 'bg-danger/20 border-danger/50 text-danger';
  if (verdict === 'SUSPICIOUS') return 'bg-suspicious/20 border-suspicious/50 text-suspicious';
  return 'bg-safe/20 border-safe/50 text-safe';
}

function verdictLabel(verdict: string) {
  if (verdict === 'PHISHING') return 'Likely a scam';
  if (verdict === 'SUSPICIOUS') return 'Worth a second look';
  return 'Looks safe';
}

function scoreCaption(score: number) {
  if (score >= 60) return "That's a high risk score";
  if (score >= 30) return 'A moderate risk score';
  return "That's a low risk score";
}

function ScoreRing({ score, verdict }: { score: number; verdict: string }) {
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (score / 100) * circumference;
  const colorClass = verdict === 'PHISHING' ? 'text-danger' : (verdict === 'SUSPICIOUS' ? 'text-suspicious' : 'text-safe');

  return (
    <div className="relative w-32 h-32 flex items-center justify-center">
      <svg className="w-full h-full transform -rotate-90">
        <circle cx="64" cy="64" r="40" stroke="currentColor" strokeWidth="8" fill="transparent" className="text-border" />
        <circle
          cx="64" cy="64" r="40" stroke="currentColor" strokeWidth="8" fill="transparent"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          className={cn("transition-all duration-1000", colorClass)}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-3xl font-bold leading-none">{score}</span>
        <span className="text-[10px] text-text-secondary mt-1">out of 100</span>
      </div>
    </div>
  );
}

function BreakdownBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = Math.round((value / max) * 100);
  return (
    <div className="mb-3">
      <div className="flex justify-between text-xs mb-1">
        <span className="text-text-secondary">{label}</span>
        <span className="text-text-secondary">{pct}%</span>
      </div>
      <div className="h-2 w-full bg-background rounded-full overflow-hidden">
        <div
          className="h-full bg-accent transition-all duration-1000"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default function InspectorPanel({ scan }: { scan: ScanResult }) {
  return (
    <div className="p-6">
      <h2 className="text-lg font-semibold mb-1">How risky is this?</h2>
      <p className="text-xs text-text-secondary mb-6">{scoreCaption(scan.risk_score)}</p>

      <div className="flex flex-col items-center mb-8">
        <ScoreRing score={scan.risk_score} verdict={scan.verdict} />
        <div className={cn("mt-4 px-4 py-1.5 rounded-full border font-semibold text-sm", verdictBg(scan.verdict))}>
          {verdictLabel(scan.verdict)}
        </div>
      </div>

      <div className="space-y-6">
        <div>
          <h3 className="text-sm font-semibold mb-3 border-b border-border pb-1">Why we think that</h3>
          <BreakdownBar label="Technical red flags" value={scan.breakdown?.technical || 0} max={25} />
          <BreakdownBar label="What it's trying to get you to do" value={scan.breakdown?.intent || 0} max={30} />
          <BreakdownBar label="Manipulation tactics" value={scan.breakdown?.social_engineering || 0} max={30} />
          <BreakdownBar label="Suspicious links" value={scan.breakdown?.urls || 0} max={15} />
          <BreakdownBar label="Does the story add up?" value={scan.breakdown?.semantic_support || 0} max={10} />
        </div>

        {scan.suspicious_evidence && scan.suspicious_evidence.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold mb-3 border-b border-border pb-1">What looks off</h3>
            <ul className="list-disc pl-4 space-y-2 text-sm text-text-secondary leading-relaxed">
              {scan.suspicious_evidence.map((evidence, i) => (
                <li key={i}>{evidence}</li>
              ))}
            </ul>
          </div>
        )}

        {scan.actionable_advice && scan.actionable_advice.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold mb-3 border-b border-border pb-1">What you should do</h3>
            <ul className="space-y-2 text-sm">
              {scan.actionable_advice.map((advice, i) => (
                <li key={i} className="flex gap-2 items-start bg-background p-3 rounded-lg border border-border leading-relaxed">
                  <span className="text-accent mt-0.5">•</span>
                  <span>{advice}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
