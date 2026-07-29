"use client";

import { useEffect, useRef } from "react";
import { useInView, useMotionValue, useSpring } from "motion/react";

interface AnimatedCounterProps {
  value: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  className?: string;
  /** Spring stiffness — lower = slower, more "weighty" settle. */
  stiffness?: number;
}

/** Counts up from 0 to `value` using a spring, once it scrolls into view.
 * Re-triggers whenever `value` changes (e.g. a new run's data loads). */
export function AnimatedCounter({
  value,
  prefix = "",
  suffix = "",
  decimals = 0,
  className,
  stiffness = 90,
}: AnimatedCounterProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-10% 0px" });
  const motionValue = useMotionValue(0);
  const spring = useSpring(motionValue, { stiffness, damping: 20 });

  useEffect(() => {
    if (isInView) motionValue.set(value);
  }, [isInView, value, motionValue]);

  useEffect(() => {
    const unsubscribe = spring.on("change", (latest) => {
      if (ref.current) {
        ref.current.textContent = `${prefix}${latest.toFixed(decimals)}${suffix}`;
      }
    });
    return unsubscribe;
  }, [spring, prefix, suffix, decimals]);

  return (
    <span ref={ref} className={className}>
      {prefix}0{suffix}
    </span>
  );
}
