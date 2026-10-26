import type { Check } from '../types';

export const previewError: Check = function* ({ preview }) {
  if (!preview?.error) return;
  yield {
    code: 'preview.error',
    level: 'error',
    title: 'The preview has an error',
    detail: preview.error,
    subject: {},
    actions: []
  };
};
