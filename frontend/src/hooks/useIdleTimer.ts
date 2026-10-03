import { useEffect, useRef, useState } from 'react';
import { IDLE_NOTICE_MS, MAX_KEEP_OPEN, idleDurations } from '../config/idleTimer';

export type IdlePhase = 'idle' | 'prompt' | 'closing';

interface Options {
  /** Run the timer only while true (panel open, Nova not typing, no human handoff, ...). */
  active: boolean;
  /** Changes whenever the user writes a message: restarts the timer and the keep-open counter. */
  activityKey: unknown;
  /** Called after the "closed due to inactivity" notice has been shown. */
  onTimeout: () => void;
}

/**
 * Silence -> "anything else?" prompt -> more silence -> "closed" notice -> onTimeout.
 * Any change of `active` or `activityKey`, and the keep-open button, restart it from zero.
 * After MAX_KEEP_OPEN keep-opens the prompt has no button (`canKeepOpen` false) and the chat
 * still closes after the same extra wait.
 */
export function useIdleTimer({ active, activityKey, onTimeout }: Options) {
  const [phase, setPhase] = useState<IdlePhase>('idle');
  const [keeps, setKeeps] = useState(0);
  const [epoch, setEpoch] = useState(0);
  const onTimeoutRef = useRef(onTimeout);
  useEffect(() => { onTimeoutRef.current = onTimeout; });

  useEffect(() => { setKeeps(0); }, [activityKey]);

  useEffect(() => {
    setPhase('idle');
    if (!active) return;
    const { promptMs, closeMs } = idleDurations();
    const timers: ReturnType<typeof setTimeout>[] = [];
    timers.push(setTimeout(() => setPhase('prompt'), promptMs));
    timers.push(setTimeout(() => {
      setPhase('closing');
      timers.push(setTimeout(() => onTimeoutRef.current(), IDLE_NOTICE_MS));
    }, promptMs + closeMs));
    return () => timers.forEach(clearTimeout);
  }, [active, activityKey, epoch]);

  const canKeepOpen = keeps < MAX_KEEP_OPEN;
  const keepOpen = () => {
    if (!canKeepOpen) return;
    setKeeps((k) => k + 1);
    setEpoch((e) => e + 1);
  };

  return { phase, canKeepOpen, keepOpen };
}
