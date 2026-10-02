import { useState } from 'react';
import { startListener } from '../lib/api';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onConnected: () => void;
}

export default function ConnectInboxModal({ isOpen, onClose, onConnected }: Props) {
  const [host, setHost] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isConnecting, setIsConnecting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsConnecting(true);
    try {
      await startListener({ host, username, app_password: password });
      onConnected();
      onClose();
      // Don't persist credentials
      setHost('');
      setUsername('');
      setPassword('');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to connect. Ensure your backend is running.';
      alert(message);
    } finally {
      setIsConnecting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-surface border border-border p-6 rounded-lg w-full max-w-md shadow-2xl">
        <h2 className="text-xl font-semibold mb-2">Connect your inbox</h2>
        <p className="text-sm text-text-secondary mb-6 leading-relaxed">
          Once connected, I'll keep an eye on new mail and let you know right away if something looks like a scam.
          Your login details go straight to your own backend running on this computer — they're never stored or sent anywhere else.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Mail server</label>
            <input
              type="text"
              required
              value={host}
              onChange={e => setHost(e.target.value)}
              placeholder="imap.gmail.com"
              className="w-full bg-background border border-border rounded-lg p-2.5 text-sm focus:outline-none focus:border-accent"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Your email address</label>
            <input
              type="email"
              required
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="you@gmail.com"
              className="w-full bg-background border border-border rounded-lg p-2.5 text-sm focus:outline-none focus:border-accent"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">App password</label>
            <input
              type="password"
              required
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Not your regular password"
              className="w-full bg-background border border-border rounded-lg p-2.5 text-sm focus:outline-none focus:border-accent"
            />
          </div>

          <div className="flex justify-end gap-3 mt-6">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm hover:bg-background transition-colors"
            >
              Not now
            </button>
            <button
              type="submit"
              disabled={isConnecting}
              className="bg-accent text-white px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              {isConnecting ? 'Connecting…' : 'Start watching my inbox'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
