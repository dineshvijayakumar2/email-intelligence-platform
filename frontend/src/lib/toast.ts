/**
 * Toast notifications — Sonner wrapper
 * Drop-in replacement for antd `message.success/error/warning/info`
 */
import { toast } from 'sonner';

export const notify = {
  success: (msg: string) => toast.success(msg),
  error: (msg: string) => toast.error(msg),
  warning: (msg: string) => toast.warning(msg),
  info: (msg: string) => toast.info(msg),
};

export { toast };
