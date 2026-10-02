import { useState, useEffect, useCallback } from 'react';
import InboxList from './components/InboxList';
import EmailView from './components/EmailView';
import InspectorPanel from './components/InspectorPanel';
import ConnectInboxModal from './components/ConnectInboxModal';
import { fetchHistory, fetchScanResult, createEventSource, fetchListenerStatus } from './lib/api';
import type { ScanHistoryItem, ScanResult } from './types';
import { Shield } from 'lucide-react';

function App() {
  const [history, setHistory] = useState<ScanHistoryItem[]>([]);
  const [selectedScan, setSelectedScan] = useState<ScanResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [listenerActive, setListenerActive] = useState(false);

  const loadHistory = useCallback(async () => {
    try {
      const data = await fetchHistory();
      setHistory(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load history');
    }
  }, []);

  const handleSelectEmail = useCallback(async (id: string) => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchScanResult(id);
      setSelectedScan(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load email details');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
    // If the backend already has a listener running (auto-started from .env,
    // or started before a page refresh), pick that up instead of showing the
    // shield as inactive until the user re-clicks "Connect".
    fetchListenerStatus()
      .then((status) => {
        if (status?.running) setListenerActive(true);
      })
      .catch(() => {
        // Backend not reachable yet — leave listenerActive as-is; the
        // "Failed to fetch" banner from loadHistory already surfaces this.
      });
  }, [loadHistory]);

  useEffect(() => {
    if (!listenerActive) return;

    const es = createEventSource();
    // The backend sends a NAMED SSE event ("scan_result"), not the default
    // "message" event, so we must use addEventListener rather than onmessage
    // — onmessage never fires for named events.
    const handleScanResult = (event: MessageEvent) => {
      try {
        const result: ScanResult = JSON.parse(event.data);
        setHistory(prev => [{
          id: result.id,
          sender: result.sender,
          subject: result.subject,
          verdict: result.verdict,
          timestamp: new Date().toISOString()
        }, ...prev]);
        setSelectedScan(result);
      } catch (err) {
        console.error('Error parsing live scan event', err);
      }
    };
    es.addEventListener('scan_result', handleScanResult as EventListener);
    es.onerror = () => {
      setListenerActive(false);
      es.close();
    };
    return () => {
      es.removeEventListener('scan_result', handleScanResult as EventListener);
      es.close();
    };
  }, [listenerActive]);

  return (
    <div className="flex h-screen bg-background text-text-primary overflow-hidden">
      {/* Left Panel */}
      <div className="w-80 border-r border-border flex flex-col bg-surface">
        <div className="p-4 border-b border-border flex justify-between items-center">
          <div>
            <h1 className="text-xl font-bold flex items-center gap-2">
              <Shield className="text-accent" />
              PhishMind
            </h1>
            <p className="text-xs text-text-secondary mt-0.5 ml-8">
              {listenerActive ? "Watching your inbox for scams" : "Your friendly inbox guard"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {listenerActive && (
              <span className="flex h-3 w-3 relative" title="Watching your inbox">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-safe opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-safe"></span>
              </span>
            )}
            <button
              onClick={() => setIsModalOpen(true)}
              className="text-xs bg-accent text-white px-3 py-1.5 rounded-lg hover:opacity-90 font-medium"
            >
              {listenerActive ? "Connected" : "Connect inbox"}
            </button>
          </div>
        </div>
        <InboxList
          items={history}
          onSelect={handleSelectEmail}
          selectedId={selectedScan?.id}
          onScanComplete={(result) => {
            setHistory(prev => [{
              id: result.id, sender: result.sender, subject: result.subject, verdict: result.verdict, timestamp: new Date().toISOString()
            }, ...prev]);
            setSelectedScan(result);
          }}
        />
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col min-w-0">
          {error && (
            <div className="bg-danger/10 text-danger p-4 border-b border-danger/20 text-center">
              {error}
            </div>
          )}
          {loading ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-3 text-text-secondary text-sm">
              <div className="animate-spin h-8 w-8 border-4 border-accent border-t-transparent rounded-full"></div>
              Reading this email…
            </div>
          ) : selectedScan ? (
            <EmailView email={selectedScan} />
          ) : (
            <div className="flex-1 flex items-center justify-center text-text-secondary text-sm max-w-sm text-center mx-auto leading-relaxed">
              Pick an email on the left to see what I found, or connect your inbox so I can watch it for you automatically.
            </div>
          )}
        </div>

        {/* Right Panel */}
        {selectedScan && !loading && (
          <div className="w-[360px] border-l border-border bg-surface overflow-y-auto">
            <InspectorPanel scan={selectedScan} />
          </div>
        )}
      </div>

      <ConnectInboxModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onConnected={() => setListenerActive(true)}
      />
    </div>
  );
}

export default App;
