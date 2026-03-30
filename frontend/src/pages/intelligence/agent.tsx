/**
 * AI Chat Agent — Conversational Q&A over the email intelligence platform.
 *
 * Uses a LangGraph ReAct agent with 6 tools (company, contact, thread,
 * quote, semantic email search, semantic operations search).
 *
 * Sprint 4 S4.4 — /insights/agent
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  Card, Input, Button, Typography, Space, Tag, Collapse, Spin, message, Empty,
} from 'antd';
import {
  SendOutlined, RobotOutlined, UserOutlined, DeleteOutlined,
  SearchOutlined, BankOutlined, MailOutlined, FileTextOutlined,
  ToolOutlined, TeamOutlined,
} from '@ant-design/icons';
import { agentChat, AgentChatResponse } from '../../services/aiService';
import { ClientSelector } from '../../components/analytics/ClientSelector';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  tools_used?: AgentChatResponse['tools_used'];
  model?: string;
  cost_usd?: number;
  processing_time_ms?: number;
  timestamp: number;
}

// ---------------------------------------------------------------------------
// Suggested starters
// ---------------------------------------------------------------------------

const SUGGESTIONS = [
  { icon: <BankOutlined />, text: 'Which companies are at risk of churning?' },
  { icon: <TeamOutlined />, text: 'Who are our top 5 customers by revenue?' },
  { icon: <MailOutlined />, text: 'What urgent emails need follow-up this week?' },
  { icon: <SearchOutlined />, text: 'Search for wide format printing deals' },
  { icon: <ToolOutlined />, text: 'What embellishment services do we offer?' },
  { icon: <FileTextOutlined />, text: 'Which accounts haven\'t been contacted in 90 days?' },
];

const TOOL_ICONS: Record<string, React.ReactNode> = {
  lookup_company_detail: <BankOutlined />,
  lookup_contact_history: <TeamOutlined />,
  lookup_thread_messages: <MailOutlined />,
  lookup_quote_detail: <FileTextOutlined />,
  semantic_search_emails: <SearchOutlined />,
  semantic_search_operations: <ToolOutlined />,
};

const TOOL_LABELS: Record<string, string> = {
  lookup_company_detail: 'Company lookup',
  lookup_contact_history: 'Contact history',
  lookup_thread_messages: 'Thread messages',
  lookup_quote_detail: 'Quote detail',
  semantic_search_emails: 'Email search',
  semantic_search_operations: 'Operations search',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const AgentPage: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [clientId, setClientId] = useState<string>('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Clear conversation when client changes
  useEffect(() => {
    setMessages([]);
  }, [clientId]);

  const handleSend = async (text?: string) => {
    const msg = (text || input).trim();
    if (!msg || loading) return;
    if (!clientId) {
      message.warning('Please select a client first');
      return;
    }

    const userMessage: ChatMessage = { role: 'user', content: msg, timestamp: Date.now() };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      // Build conversation history (excluding the new message)
      const history = messages.map(m => ({ role: m.role, content: m.content }));

      const result = await agentChat(msg, clientId, history);

      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: result.response,
        tools_used: result.tools_used,
        model: result.model,
        cost_usd: result.cost_usd,
        processing_time_ms: result.processing_time_ms,
        timestamp: Date.now(),
      };
      setMessages(prev => [...prev, assistantMessage]);
    } catch (err: any) {
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content: `Sorry, I encountered an error: ${err.message || 'Please try again.'}`,
        timestamp: Date.now(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="fade-in-up" style={{ maxWidth: 900, margin: '0 auto', padding: '24px 16px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}><RobotOutlined /> AI Assistant</Title>
          <Text type="secondary">Ask questions about your customers, emails, and operations</Text>
        </div>
        <Space>
          {messages.length > 0 && (
            <Button
              icon={<DeleteOutlined />}
              onClick={() => setMessages([])}
              size="small"
            >
              Clear
            </Button>
          )}
          <ClientSelector value={clientId} onChange={setClientId} />
        </Space>
      </div>

      {/* Chat area */}
      <Card
        className="glass-card"
        bodyStyle={{
          height: 'calc(100vh - 320px)',
          minHeight: 400,
          display: 'flex',
          flexDirection: 'column',
          padding: 0,
        }}
      >
        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
          {messages.length === 0 && !loading ? (
            <div style={{ textAlign: 'center', paddingTop: 60 }}>
              <RobotOutlined style={{ fontSize: 48, color: '#bbb', marginBottom: 16 }} />
              <Title level={5} style={{ color: '#888' }}>How can I help you today?</Title>
              <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>
                Try one of these questions or ask your own
              </Text>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', maxWidth: 600, margin: '0 auto' }}>
                {SUGGESTIONS.map((s, i) => (
                  <Button
                    key={i}
                    icon={s.icon}
                    onClick={() => handleSend(s.text)}
                    style={{ textAlign: 'left' }}
                    disabled={!clientId}
                  >
                    {s.text}
                  </Button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    marginBottom: 16,
                  }}
                >
                  <div
                    style={{
                      maxWidth: '80%',
                      padding: '10px 16px',
                      borderRadius: 12,
                      background: msg.role === 'user' ? '#1677ff' : '#f5f5f5',
                      color: msg.role === 'user' ? '#fff' : '#333',
                    }}
                  >
                    {msg.role === 'assistant' ? (
                      <>
                        {/* Tool usage tags */}
                        {msg.tools_used && msg.tools_used.length > 0 && (
                          <div style={{ marginBottom: 8 }}>
                            <Collapse
                              size="small"
                              ghost
                              items={[{
                                key: 'tools',
                                label: (
                                  <Text type="secondary" style={{ fontSize: 11 }}>
                                    Used {msg.tools_used.length} tool{msg.tools_used.length > 1 ? 's' : ''}
                                  </Text>
                                ),
                                children: (
                                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                                    {msg.tools_used.map((t, ti) => (
                                      <Tag key={ti} icon={TOOL_ICONS[t.tool_name]} color="processing">
                                        {TOOL_LABELS[t.tool_name] || t.tool_name}
                                      </Tag>
                                    ))}
                                  </div>
                                ),
                              }]}
                            />
                          </div>
                        )}
                        <div style={{ fontSize: 14, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                          {msg.content}
                        </div>
                        {/* Cost footer */}
                        {msg.model && (
                          <Text type="secondary" style={{ fontSize: 10, display: 'block', marginTop: 6 }}>
                            {msg.model} | ${msg.cost_usd?.toFixed(4)} | {((msg.processing_time_ms || 0) / 1000).toFixed(1)}s
                          </Text>
                        )}
                      </>
                    ) : (
                      <Text style={{ color: '#fff' }}>{msg.content}</Text>
                    )}
                  </div>
                </div>
              ))}

              {/* Loading indicator */}
              {loading && (
                <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 16 }}>
                  <div style={{ padding: '12px 20px', borderRadius: 12, background: '#f5f5f5' }}>
                    <Space>
                      <Spin size="small" />
                      <Text type="secondary">Thinking...</Text>
                    </Space>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* Input area */}
        <div style={{ padding: '12px 16px', borderTop: '1px solid #f0f0f0' }}>
          <Space.Compact style={{ width: '100%' }}>
            <TextArea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={clientId ? 'Ask about your customers, emails, or operations...' : 'Select a client to start'}
              autoSize={{ minRows: 1, maxRows: 4 }}
              disabled={loading || !clientId}
              style={{ flex: 1 }}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={() => handleSend()}
              disabled={!input.trim() || loading || !clientId}
              style={{ height: 'auto' }}
            />
          </Space.Compact>
        </div>
      </Card>
    </div>
  );
};

export default AgentPage;
