// Motion vocabulary for the whole interface (Motion, motion/react). One ease, three durations, and the variants every list and
// page uses, so movement feels the same everywhere. Components read useReducedMotion themselves where a variant would still move.
import type { Transition, Variants } from "motion/react";

export const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];
export const DUR = { fast: 0.16, base: 0.24, slow: 0.4 } as const;

export const spring: Transition = { type: "spring", stiffness: 520, damping: 42, mass: 0.8 };
export const softSpring: Transition = { type: "spring", stiffness: 300, damping: 30 };

/** A page: a short rise and fade in, a fade out. */
export const pageVariants: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: DUR.base, ease: EASE } },
  exit: { opacity: 0, transition: { duration: DUR.fast, ease: "easeIn" } },
};

/** A list: its rows arrive one after the other (40 ms apart, never more than ~0.5 s in all). */
export const listVariants: Variants = {
  initial: {},
  animate: { transition: { staggerChildren: 0.04, delayChildren: 0.02 } },
};
export const rowVariants: Variants = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0, transition: { duration: DUR.base, ease: EASE } },
  exit: { opacity: 0, scale: 0.98, transition: { duration: DUR.fast } },
};

/** A panel or dialog: scale from 98 % with a fade. */
export const panelVariants: Variants = {
  initial: { opacity: 0, scale: 0.98, y: 4 },
  animate: { opacity: 1, scale: 1, y: 0, transition: { duration: DUR.base, ease: EASE } },
  exit: { opacity: 0, scale: 0.98, transition: { duration: DUR.fast } },
};

/** A side sheet from the right. */
export const sheetVariants: Variants = {
  initial: { opacity: 0, x: 24 },
  animate: { opacity: 1, x: 0, transition: { duration: DUR.slow, ease: EASE } },
  exit: { opacity: 0, x: 24, transition: { duration: DUR.base, ease: "easeIn" } },
};

export const fade: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: DUR.base } },
  exit: { opacity: 0, transition: { duration: DUR.fast } },
};

/** The small scale on press, for anything that acts. */
export const press = { whileTap: { scale: 0.97 } } as const;
