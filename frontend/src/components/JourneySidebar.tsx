import { Link2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ThreadJourneyPanel } from './ThreadJourneyPanel';

interface Props {
  threadId: string;
  clientId: string;
  isOpen: boolean;
  onToggle: () => void;
}

export function JourneySidebar({ threadId, clientId, isOpen, onToggle }: Props) {
  return (
    <div className={cn(
      'border-l bg-white flex flex-col shrink-0 transition-all duration-200 overflow-hidden relative',
      isOpen ? 'w-[380px]' : 'w-0',
    )}>
      <div className="flex items-center justify-between px-3 py-2 border-b bg-slate-50/50 shrink-0">
        <span className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
          <Link2 className="h-4 w-4 text-primary" />Journey
        </span>
        <button onClick={onToggle} className="p-1 rounded hover:bg-slate-100" title="Close journey panel">
          <X className="h-4 w-4 text-slate-400" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        <ThreadJourneyPanel threadId={threadId} clientId={clientId} />
      </div>
    </div>
  );
}
