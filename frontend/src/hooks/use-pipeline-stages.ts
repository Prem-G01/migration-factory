import { useEffect, useRef, useState } from "react";

/** Purely cosmetic stage progression — there's no real progress channel
 * from the API, so this just gives the wait some visual life over
 * `totalDurationMs`. The caller is expected to clear/ignore this the
 * moment a real API response actually lands, never block on it. */
export function usePipelineStages(totalDurationMs = 4000) {
  const [stageIndex, setStageIndex] = useState(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clear = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };

  useEffect(() => clear, []);

  const start = (stageCount: number) => {
    clear();
    setStageIndex(0);
    const step = totalDurationMs / stageCount;
    for (let i = 1; i < stageCount; i++) {
      timers.current.push(setTimeout(() => setStageIndex(i), Math.round(step * i)));
    }
  };

  return { stageIndex, start, clear };
}
