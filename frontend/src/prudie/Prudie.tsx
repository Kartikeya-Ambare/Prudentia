import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  type CSSProperties,
} from 'react';
import { mountPrudie, type IdleAction, type PrudieHandle, type PrudieState } from './engine';

export interface PrudieProps {
  /** What Prudie is doing. Change it and Prudie moves into the new action. */
  state?: PrudieState;
  /** px number or any CSS size. Prudie keeps a 5:6 aspect ratio. */
  size?: number | string;
  /** Eyes follow the cursor inside followRadius. Default true. */
  followPointer?: boolean;
  /** Radius in px around Prudie inside which the eyes follow the cursor. Default 460. */
  followRadius?: number;
  /** Seconds of rest between idle actions as [min, max]. null = off. Default [2, 3]. */
  idleEvery?: [number, number] | null;
  /** Which idle actions may play. Default all of them. */
  idleActions?: IdleAction[];
  /** Seconds without mouse movement before Prudie naps. null = never. Default 25. */
  napAfter?: number | null;
  /** Raise a palm when the cursor comes close; click for a high five. Default true. */
  highFive?: boolean;
  /** What Prudie says after thumbs up. Default ['Task done!', "Done! What's next?"]. */
  doneLines?: string[];
  /** Hover bubble text. '' = no bubble. */
  greeting?: string;
  bubble?: 'top' | 'left' | 'right';
  /** Viewport point Prudie looks at in the 'look' state (e.g. the chat input). */
  lookTarget?: { x: number; y: number } | null;
  /** Fired when wave / thumbsup finished by themselves. Use it to reset your own state to 'idle'. */
  onSettle?: (finished: PrudieState) => void;
  className?: string;
  style?: CSSProperties;
}

export interface PrudieRef {
  wave(): void;
  poke(): void;
  playIdle(action: IdleAction): void;
  say(text: string, ms?: number): void;
  nap(): void;
  wake(): void;
}

export const Prudie = forwardRef<PrudieRef, PrudieProps>(function Prudie(
  {
    state = 'idle',
    size = 180,
    followPointer = true,
    followRadius = 460,
    idleEvery = [2, 3],
    idleActions,
    napAfter = 25,
    highFive = true,
    doneLines,
    greeting,
    bubble = 'top',
    lookTarget = null,
    onSettle,
    className,
    style,
  },
  ref,
) {
  const host = useRef<HTMLDivElement>(null);
  const handle = useRef<PrudieHandle | null>(null);
  const settle = useRef(onSettle);
  settle.current = onSettle;

  useEffect(() => {
    handle.current = mountPrudie(host.current!, {
      state,
      followPointer,
      followRadius,
      idleEvery,
      idleActions,
      napAfter,
      highFive,
      doneLines,
      greeting,
      bubble,
      onSettle: (s) => settle.current?.(s),
    });
    return () => handle.current?.destroy();
    // mount once per structural option; state changes below never re-mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [followPointer, followRadius, idleEvery?.[0], idleEvery?.[1], idleActions?.join(), napAfter, highFive, doneLines?.join(), greeting, bubble]);

  useEffect(() => handle.current?.setState(state), [state]);
  useEffect(() => handle.current?.setLookTarget(lookTarget), [lookTarget?.x, lookTarget?.y]);

  useImperativeHandle(
    ref,
    () => ({
      wave: () => handle.current?.wave(),
      poke: () => handle.current?.poke(),
      playIdle: (a: IdleAction) => handle.current?.playIdle(a),
      say: (text: string, ms?: number) => handle.current?.say(text, ms),
      nap: () => handle.current?.nap(),
      wake: () => handle.current?.wake(),
    }),
    [],
  );

  const w = typeof size === 'number' ? `${size}px` : size;
  return <div ref={host} className={className} style={{ width: w, aspectRatio: '300 / 360', ...style }} />;
});

export default Prudie;
