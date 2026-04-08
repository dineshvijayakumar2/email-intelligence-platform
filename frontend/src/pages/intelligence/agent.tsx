/**
 * AI Chat Agent — Zero antd.
 * Conversational Q&A with LangGraph ReAct agent.
 */

import React, { useState, useRef, useEffect } from 'react';
import { Bot, Send, Trash2, Search, Building2, Mail, FileText, Wrench, Users, ChevronDown } from 'lucide-react';
import { Spinner } from '@/lib/icons';
import { StatusBadge } from '@/components/ui/status-badge';
import { toast } from '@/lib/toast';
import { useClient } from '../../contexts/ClientContext';
import { agentChatStream, type AgentChatResponse } from '../../services/aiService';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import Markdown from 'react-markdown';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  tools_used?: AgentChatResponse['tools_used'];
  model?: string;
  cost_usd?: number;
  processing_time_ms?: number;
  timestamp: number;
}

const SUGGESTIONS = [
  { icon: <Building2 className="h-3.5 w-3.5" />, text: 'Which companies are at risk of churning?' },
  { icon: <Users className="h-3.5 w-3.5" />, text: 'Who are our top 5 customers by revenue?' },
  { icon: <Mail className="h-3.5 w-3.5" />, text: 'What urgent emails need follow-up this week?' },
  { icon: <Search className="h-3.5 w-3.5" />, text: 'Search for wide format printing deals' },
  { icon: <Wrench className="h-3.5 w-3.5" />, text: 'What embellishment services do we offer?' },
  { icon: <FileText className="h-3.5 w-3.5" />, text: 'Which accounts haven\'t been contacted in 90 days?' },
];

const TOOL_LABELS: Record<string, string> = {
  portfolio_summary: 'Portfolio summary', account_ranking: 'Account ranking',
  search_emails: 'Email search', search_contacts: 'Contact search',
  thread_overview: 'Thread overview', company_analytics: 'Company analytics',
  lookup_company_detail: 'Company lookup', lookup_contact_history: 'Contact history',
  lookup_thread_messages: 'Thread messages', lookup_quote_detail: 'Quote detail',
  semantic_search_emails: 'Semantic email search', semantic_search_operations: 'Operations search',
};

const AgentPage: React.FC = () => {
  const { clientId } = useClient();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, loading]);
  useEffect(() => { setMessages([]); }, [clientId]);

  const handleSend = async (text?: string) => {
    const msg = (text || input).trim();
    if (!msg || loading) return;
    if (!clientId) { toast.warning('Please select a client first'); return; }

    const userMessage: ChatMessage = { role: 'user', content: msg, timestamp: Date.now() };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    const placeholderId = Date.now();
    const placeholder: ChatMessage = { role: 'assistant', content: '', tools_used: [], timestamp: placeholderId };
    setMessages(prev => [...prev, placeholder]);

    try {
      const history = messages.map(m => ({ role: m.role, content: m.content }));
      await agentChatStream(msg, clientId, history,
        (content) => { setMessages(prev => prev.map(m => m.timestamp === placeholderId ? { ...m, content: m.content + content } : m)); },
        (tool) => { setMessages(prev => prev.map(m => m.timestamp === placeholderId ? { ...m, tools_used: [...(m.tools_used || []), { tool_name: tool }] } : m)); },
        (tool, output) => {
          setMessages(prev => prev.map(m => {
            if (m.timestamp !== placeholderId) return m;
            const tools = [...(m.tools_used || [])];
            for (let i = tools.length - 1; i >= 0; i--) {
              if (tools[i].tool_name === tool) { tools[i] = { ...tools[i], tool_output_preview: output }; break; }
            }
            return { ...m, tools_used: tools };
          }));
        },
        (response, toolsUsed, processingTimeMs) => {
          setMessages(prev => prev.map(m => m.timestamp === placeholderId
            ? { ...m, content: response || m.content, tools_used: toolsUsed.map(t => ({ tool_name: t })), processing_time_ms: processingTimeMs }
            : m));
        },
        (detail) => { setMessages(prev => prev.map(m => m.timestamp === placeholderId ? { ...m, content: `Sorry, I encountered an error: ${detail}` } : m)); },
      );
    } catch (err: any) {
      setMessages(prev => prev.map(m => m.timestamp === placeholderId ? { ...m, content: `Sorry, I encountered an error: ${err.message || 'Please try again.'}` } : m));
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <PageShell>
      <div className="max-w-[900px] mx-auto">
        <div className="flex items-center justify-between mb-4">
          <PageHeader title="AI Assistant" description="Ask questions about your customers, emails, and operations" />
          {messages.length > 0 && (
            <button onClick={() => setMessages([])}
              className="h-7 px-2.5 text-xs rounded-md border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1.5">
              <Trash2 className="h-3 w-3" /> Clear
            </button>
          )}
        </div>

        {/* Chat area */}
        <div className="rounded-lg border bg-white shadow-sm flex flex-col" style={{ height: 'calc(100vh - 220px)', minHeight: 400 }}>
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-5 py-4">
            {messages.length === 0 && !loading ? (
              <div className="text-center pt-16">
                <Bot className="h-12 w-12 text-slate-300 mx-auto mb-4" />
                <h3 className="text-sm font-medium text-slate-500 mb-1">How can I help you today?</h3>
                <p className="text-xs text-slate-400 mb-6">Try one of these questions or ask your own</p>
                <div className="flex flex-wrap gap-2 justify-center max-w-[600px] mx-auto">
                  {SUGGESTIONS.map((s, i) => (
                    <button key={i} onClick={() => handleSend(s.text)} disabled={!clientId}
                      className="inline-flex items-center gap-2 px-3 py-2 text-xs text-slate-600 rounded-lg border border-slate-200 hover:border-primary/30 hover:bg-primary/5 transition-colors disabled:opacity-50 text-left">
                      {s.icon} {s.text}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {messages.map((msg, idx) => (
                  <div key={idx} className={`flex mb-4 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[80%] px-4 py-2.5 rounded-xl ${msg.role === 'user' ? 'bg-primary text-white' : 'bg-slate-50 text-slate-800'}`}>
                      {msg.role === 'assistant' ? (
                        <>
                          {msg.tools_used && msg.tools_used.length > 0 && (
                            <div className="flex flex-wrap gap-1 mb-2">
                              {msg.tools_used.map((t, ti) => (
                                <StatusBadge key={ti} variant="info" size="sm">
                                  {TOOL_LABELS[t.tool_name] || t.tool_name}
                                </StatusBadge>
                              ))}
                            </div>
                          )}
                          <div className="text-sm prose prose-sm prose-slate max-w-none agent-markdown">
                            <Markdown>{msg.content}</Markdown>
                          </div>
                          {msg.processing_time_ms != null && (
                            <p className="text-[10px] text-slate-400 mt-2">
                              {((msg.processing_time_ms || 0) / 1000).toFixed(1)}s
                            </p>
                          )}
                        </>
                      ) : (
                        <p className="text-sm">{msg.content}</p>
                      )}
                    </div>
                  </div>
                ))}
                {loading && (
                  <div className="flex justify-start mb-4">
                    <div className="px-4 py-3 rounded-xl bg-slate-50 inline-flex items-center gap-2">
                      <Spinner className="h-4 w-4 animate-spin text-primary" />
                      <span className="text-xs text-slate-400">Thinking...</span>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* Input area */}
          <div className="px-4 py-3 border-t">
            <div className="flex gap-2">
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={clientId ? 'Ask about your customers, emails, or operations...' : 'Select a client to start'}
                rows={1}
                disabled={loading || !clientId}
                className="flex-1 px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-50"
              />
              <button
                onClick={() => handleSend()}
                disabled={!input.trim() || loading || !clientId}
                className="h-9 w-9 shrink-0 rounded-lg bg-primary text-white hover:bg-primary-dark disabled:opacity-50 flex items-center justify-center"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  );
};

export default AgentPage;
