import { useState } from 'react';
import type { ScanHistoryItem, ScanResult } from '../types';
import { cn } from '../lib/utils';
import { scanEmail } from '../lib/api';

interface Props {
  items: ScanHistoryItem[];
  onSelect: (id: string) => void;
  selectedId?: string;
  onScanComplete: (result: ScanResult) => void;
}

export default function InboxList({ items, onSelect, selectedId, onScanComplete }: Props) {
  const [pasteContent, setPasteContent] = useState('');
  const [isScanning, setIsScanning] = useState(false);

  const handleScan = async () => {
    if (!pasteContent.trim()) return;
    try {
      setIsScanning(true);
      const res = await scanEmail(pasteContent);
      onScanComplete(res);
      setPasteContent('');
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Scan failed');
    } finally {
      setIsScanning(false);
    }
  };

  const verdictColor = (verdict: string) => {
    if (verdict === 'PHISHING') return 'bg-danger';
    if (verdict === 'SUSPICIOUS') return 'bg-suspicious';
    return 'bg-safe';
  };

  const verdictTitle = (verdict: string) => {
    if (verdict === 'PHISHING') return 'Likely a scam';
    if (verdict === 'SUSPICIOUS') return 'Worth a second look';
    return 'Looks safe';
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="p-4 border-b border-border space-y-2">
        <textarea
          value={pasteContent}
          onChange={(e) => setPasteContent(e.target.value)}
          placeholder="Not sure about an email? Paste it here and I'll take a look..."
          className="w-full h-24 bg-background border border-border rounded-lg p-2.5 text-sm focus:outline-none focus:border-accent resize-none placeholder:text-text-secondary/70"
        />
        <button
          onClick={handleScan}
          disabled={isScanning || !pasteContent.trim()}
          className="w-full bg-accent text-white py-2 rounded-lg hover:opacity-90 disabled:opacity-50 transition-opacity font-medium"
        >
          {isScanning ? 'Reading it now…' : 'Check this email'}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {items.length === 0 ? (
          <div className="p-4 text-center text-text-secondary text-sm leading-relaxed">
            Nothing checked yet — paste an email above, or connect your inbox and I'll watch it for you.
          </div>
        ) : (
          items.map(item => (
            <div
              key={item.id}
              onClick={() => onSelect(item.id)}
              className={cn(
                "p-4 border-b border-border cursor-pointer hover:bg-background/50 transition-colors flex gap-3",
                selectedId === item.id ? "bg-background/80" : ""
              )}
            >
              <div className="mt-1">
                <div className={cn("w-3 h-3 rounded-full", verdictColor(item.verdict))} title={verdictTitle(item.verdict)} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{item.sender}</div>
                <div className="text-xs text-text-secondary truncate">{item.subject}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
