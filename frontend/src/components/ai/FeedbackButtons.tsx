/**
 * FeedbackButtons — Thumbs up/down with structured override. Zero antd.
 */

import React, { useState } from 'react';
import { ThumbsUp, ThumbsDown, CheckCircle } from 'lucide-react';
import { toast } from '@/lib/toast';
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
  const [feedbackField, setFeedbackField] = useState('');
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleCorrect = async () => {
    setSubmitting(true);
    const result = await feedbackApi.submit(emailId, { feedback: 'correct' });
    setSubmitting(false);
    if (result) {
      toast.success('Feedback saved');
      onFeedbackSubmitted?.('correct');
    } else {
      toast.error('Failed to save feedback');
    }
  };

  const submitIncorrect = async () => {
    setSubmitting(true);
    const result = await feedbackApi.submit(emailId, {
      feedback: 'incorrect',
      feedback_field: feedbackField || undefined,
      note: note || undefined,
    });
    setSubmitting(false);
    if (result) {
      toast.success('Feedback saved');
      setShowOverride(false);
      onFeedbackSubmitted?.('incorrect');
    } else {
      toast.error('Failed to save feedback');
    }
  };

  if (currentFeedback) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-slate-400">
        <CheckCircle className="h-3.5 w-3.5 text-success" />
        Marked as {currentFeedback}
      </span>
    );
  }

  if (showOverride) {
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <select
            value={feedbackField}
            onChange={e => setFeedbackField(e.target.value)}
            className="h-7 px-2 text-xs rounded border border-slate-200 bg-white"
          >
            <option value="">What was wrong?</option>
            {FIELD_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <input
            type="text"
            placeholder="Optional note"
            value={note}
            onChange={e => setNote(e.target.value)}
            className="h-7 px-2 text-xs rounded border border-slate-200 bg-white w-40"
          />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={submitIncorrect}
            disabled={submitting}
            className="h-7 px-3 text-xs font-medium text-white bg-primary rounded hover:bg-primary-dark disabled:opacity-50"
          >
            Submit
          </button>
          <button
            onClick={() => setShowOverride(false)}
            className="h-7 px-3 text-xs rounded border border-slate-200 hover:bg-slate-50"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="inline-flex items-center gap-1">
      <button
        onClick={handleCorrect}
        disabled={submitting}
        className="p-1 rounded hover:bg-slate-100 text-slate-400 hover:text-success disabled:opacity-50"
        title="Correct classification"
      >
        <ThumbsUp className="h-3.5 w-3.5" />
      </button>
      <button
        onClick={() => setShowOverride(true)}
        className="p-1 rounded hover:bg-slate-100 text-slate-400 hover:text-destructive"
        title="Incorrect — tell us what's wrong"
      >
        <ThumbsDown className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};

export default FeedbackButtons;
