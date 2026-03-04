/**
 * FeedbackButtons — Thumbs up/down with structured override.
 *
 * On "incorrect", shows a dropdown to select which field was wrong
 * + optional correct value. Stores structured feedback (not just "bad").
 */

import React, { useState } from 'react';
import { Button, Space, Select, Input, message, Tooltip } from 'antd';
import { LikeOutlined, DislikeOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { feedbackApi } from '../../services/aiService';
import type { FeedbackType } from '../../types/ai';

interface FeedbackButtonsProps {
  emailId: string;
  currentFeedback?: FeedbackType | null;
  onFeedbackSubmitted?: (feedback: FeedbackType) => void;
}

const FIELD_OPTIONS = [
  { value: 'intent', label: 'Intent' },
  { value: 'bucket', label: 'Bucket' },
  { value: 'sentiment', label: 'Sentiment' },
  { value: 'urgency', label: 'Urgency' },
];

export const FeedbackButtons: React.FC<FeedbackButtonsProps> = ({
  emailId,
  currentFeedback,
  onFeedbackSubmitted,
}) => {
  const [showOverride, setShowOverride] = useState(false);
  const [feedbackField, setFeedbackField] = useState<string | undefined>();
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleCorrect = async () => {
    setSubmitting(true);
    const result = await feedbackApi.submit(emailId, { feedback: 'correct' });
    setSubmitting(false);
    if (result) {
      message.success('Feedback saved');
      onFeedbackSubmitted?.('correct');
    } else {
      message.error('Failed to save feedback');
    }
  };

  const handleIncorrect = () => {
    setShowOverride(true);
  };

  const submitIncorrect = async () => {
    setSubmitting(true);
    const result = await feedbackApi.submit(emailId, {
      feedback: 'incorrect',
      feedback_field: feedbackField,
      note: note || undefined,
    });
    setSubmitting(false);
    if (result) {
      message.success('Feedback saved');
      setShowOverride(false);
      onFeedbackSubmitted?.('incorrect');
    } else {
      message.error('Failed to save feedback');
    }
  };

  // Already submitted
  if (currentFeedback) {
    return (
      <Space>
        <CheckCircleOutlined style={{ color: '#52c41a' }} />
        <span style={{ fontSize: 12, color: '#999' }}>
          Marked as {currentFeedback}
        </span>
      </Space>
    );
  }

  if (showOverride) {
    return (
      <Space direction="vertical" size="small" style={{ width: '100%' }}>
        <Space>
          <Select
            placeholder="What was wrong?"
            options={FIELD_OPTIONS}
            value={feedbackField}
            onChange={setFeedbackField}
            style={{ width: 140 }}
            size="small"
          />
          <Input
            placeholder="Optional note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            size="small"
            style={{ width: 200 }}
          />
        </Space>
        <Space>
          <Button size="small" type="primary" onClick={submitIncorrect} loading={submitting}>
            Submit
          </Button>
          <Button size="small" onClick={() => setShowOverride(false)}>
            Cancel
          </Button>
        </Space>
      </Space>
    );
  }

  return (
    <Space>
      <Tooltip title="Correct classification">
        <Button
          icon={<LikeOutlined />}
          size="small"
          onClick={handleCorrect}
          loading={submitting}
        />
      </Tooltip>
      <Tooltip title="Incorrect — tell us what's wrong">
        <Button
          icon={<DislikeOutlined />}
          size="small"
          onClick={handleIncorrect}
        />
      </Tooltip>
    </Space>
  );
};

export default FeedbackButtons;
