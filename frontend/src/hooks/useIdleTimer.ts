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
 *
 * Wake-safe: each wait is checked against Date.now(), and the close countdown starts when the
 * prompt is actually shown, so a sleeping laptop or frozen tab never skips the prompt.
 */
export function useIdleTimer({ active, activityKey, onTimeout }: Options) {
  const [keepState, setKeepState] = useState({ key: activityKey, count: 0 });
  const [epoch, setEpoch] = useState(0);
  const [stored, setStored] = useState<{ token: string; phase: IdlePhase }>({ token: '', phase: 'idle' });
  const onTimeoutRef = useRef(onTimeout);
  useEffect(() => { onTimeoutRef.current = onTimeout; });

  // Derived during render: the counter belongs to one activityKey, the phase to one run.
  const keeps = Object.is(keepState.key, activityKey) ? keepState.count : 0;
  const token = `${String(activityKey)}|${epoch}`;
  const phase: IdlePhase = active && stored.token === token ? stored.phase : 'idle';

  useEffect(() => {
    if (!active) return;
    const { promptMs, closeMs } = idleDurations();
    const timers: ReturnType<typeof setTimeout>[] = [];
    const wait = (ms: number, then: () => void) => {
      const since = Date.now();
      const arm = (left: number) => {
        timers.push(setTimeout(() => {
          const remaining = ms - (Date.now() - since);
          if (remaining > 0) arm(remaining); // fired early: wait the rest
          else then();
        }, left));
      };
      arm(ms);
    };
    wait(promptMs, () => {
      setStored({ token, phase: 'prompt' }); // the close countdown starts now, not at the old silence
      wait(closeMs, () => {
        setStored({ token, phase: 'closing' });
        timers.push(setTimeout(() => onTimeoutRef.current(), IDLE_NOTICE_MS));
      });
    });
    return () => timers.forEach(clearTimeout);
  }, [active, token]);

  const canKeepOpen = keeps < MAX_KEEP_OPEN;
  const keepOpen = () => {
    if (!canKeepOpen) return;
    setKeepState({ key: activityKey, count: keeps + 1 });
    setEpoch((e) => e + 1);
  };

  return { phase, canKeepOpen, keepOpen };
}
