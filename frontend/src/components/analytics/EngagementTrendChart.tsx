import React, { useEffect, useState } from 'react';
import { Spin, Empty } from 'antd';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { metricHistoryApi, type MetricHistoryEntry } from '../../services/analyticsService';
import { formatDate } from '../../utils/dateUtils';

interface Props {
  entityType: 'contact' | 'company';
  entityId: string;
}

export const EngagementTrendChart: React.FC<Props> = ({ entityType, entityId }) => {
  const [data, setData] = useState<MetricHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!entityId) return;
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      try {
        const history = await metricHistoryApi.get(entityType, entityId, 30);
        if (!cancelled) setData(history);
      } catch {
        // silently fail — chart simply won't render
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [entityType, entityId]);

  if (loading) return <Spin size="small" style={{ display: 'block', margin: '20px auto' }} />;
  if (!data.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No score history yet" />;

  const chartData = data.map((d) => ({
    date: formatDate(d.calculated_at),
    score: d.engagement_score,
    responseTime: d.response_time_score,
    replyRate: d.reply_rate_score,
    frequency: d.frequency_score,
    recency: d.recency_score,
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
        <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
        <Tooltip />
        <Line type="monotone" dataKey="score" name="Engagement" stroke="#667eea" strokeWidth={2} dot={{ r: 3 }} />
        <Line type="monotone" dataKey="responseTime" name="Response Time" stroke="#52c41a" strokeWidth={1} dot={false} strokeDasharray="4 2" />
        <Line type="monotone" dataKey="replyRate" name="Reply Rate" stroke="#faad14" strokeWidth={1} dot={false} strokeDasharray="4 2" />
        <Line type="monotone" dataKey="recency" name="Recency" stroke="#eb2f96" strokeWidth={1} dot={false} strokeDasharray="4 2" />
      </LineChart>
    </ResponsiveContainer>
  );
};
