import type { ScanResult } from '../types';
import { cn } from '../lib/utils';
import { ShieldCheck, ShieldAlert, MailWarning } from 'lucide-react';

const BANNER_COPY: Record<string, { headline: string; icon: typeof MailWarning }> = {
  PHISHING: { headline: "This looks like a scam", icon: MailWarning },
  SUSPICIOUS: { headline: "Something about this feels off", icon: ShieldAlert },
};

export default function EmailView({ email }: { email: ScanResult }) {
  const isSuspicious = email.verdict === 'SUSPICIOUS' || email.verdict === 'PHISHING';
  const bannerColor = email.verdict === 'PHISHING' ? 'bg-danger' : 'bg-suspicious';
  const banner = BANNER_COPY[email.verdict];
  const isTranslated = !!email.translated_body && email.detected_language && email.detected_language !== 'en';
  const displaySubject = isTranslated && email.translated_subject ? email.translated_subject : email.subject;
  const displayBody = isTranslated ? email.translated_body! : email.body;

  return (
    <div className="flex-1 flex flex-col overflow-y-auto bg-background">
      {isSuspicious && banner && (
        <div className={cn("p-4 text-white animate-in slide-in-from-top-4", bannerColor)}>
          <div className="font-bold flex items-center gap-2 text-base">
            <banner.icon className="w-5 h-5 shrink-0" />
            {banner.headline}
          </div>
          <div className="text-sm opacity-90 mt-1 leading-relaxed">{email.explanation}</div>
        </div>
      )}

      <div className="p-8 max-w-4xl mx-auto w-full">
        <div className="border-b border-border pb-6 mb-6">
          <h2 className="text-2xl font-semibold mb-4 leading-snug">{displaySubject}</h2>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="font-medium text-text-secondary">From {email.sender}</div>
            {email.claimed_brand && email.is_brand_verifiable === false && (
              <div className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border bg-surface text-text-secondary border-border">
                <ShieldAlert className="w-3 h-3" />
                {`Says it's from ${email.claimed_brand}, but we can't confirm that`}
              </div>
            )}
            {email.claimed_brand && email.is_brand_verifiable !== false && (
              <div className={cn(
                "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border",
                email.is_brand_verified
                  ? "bg-safe/10 text-safe border-safe/20"
                  : "bg-danger/10 text-danger border-danger/20"
              )}>
                {email.is_brand_verified ? <ShieldCheck className="w-3 h-3" /> : <ShieldAlert className="w-3 h-3" />}
                {email.is_brand_verified ? `Really from ${email.claimed_brand}` : `Pretending to be ${email.claimed_brand}`}
              </div>
            )}
            {isTranslated && (
              <div className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border bg-indigo-50 text-accent border-indigo-100">
                Translated from {email.detected_language?.toUpperCase()} so you can read it
              </div>
            )}
          </div>
        </div>

        <div className="whitespace-pre-wrap text-[15px] leading-relaxed bg-surface p-6 rounded-xl border border-border">
          {displayBody}
        </div>

        {isTranslated && (
          <details className="mt-4">
            <summary className="cursor-pointer text-xs text-text-secondary select-none hover:text-text-primary transition-colors">
              See the original message ({email.detected_language?.toUpperCase()})
            </summary>
            <div className="whitespace-pre-wrap text-sm leading-relaxed bg-surface/60 p-6 rounded-xl border border-border mt-2 text-text-secondary">
              <div className="font-semibold mb-2">{email.subject}</div>
              {email.body}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}
