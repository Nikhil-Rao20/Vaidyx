// The React Bits Stepper (vendor/Stepper.tsx, MIT) dressed in our tokens: the frame is the page card, the active step
// and the Continue button are teal, the text follows the theme. Used by the profile set-up, the New Case File flow and
// the admin guided set-up.
import type { ComponentProps, CSSProperties, ReactNode } from "react";
import VendorStepper, { Step as VendorStep } from "@/components/vendor/Stepper";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

export const Step = VendorStep;

const TOKENS: CSSProperties = {
  "--stepper-frame": "var(--card)",
  "--stepper-frame-edge": "var(--border)",
  "--stepper-frame-highlight": "transparent",
  "--stepper-frame-shadow": "var(--shadow-outer)",
  "--stepper-tile": "var(--card)",
  "--stepper-tile-edge": "var(--border-strong)",
  "--stepper-tile-highlight": "transparent",
  "--stepper-tile-shadow": "var(--shadow-inner)",
  "--stepper-well": "var(--muted)",
  "--stepper-track": "var(--border)",
  "--stepper-ink": "var(--foreground)",
  "--stepper-muted": "var(--muted-foreground)",
  "--stepper-faint": "var(--border-strong)",
  "--stepper-ring": "var(--ring)",
  "--stepper-solid": "var(--primary)",
  "--stepper-solid-ink": "var(--primary-foreground)",
  "--stepper-hover": "brightness(0.97)",
  "--stepper-hover-fill": "var(--accent)",
  "--stepper-solid-hover": "brightness(0.92)",
  "--stepper-press": "brightness(0.9)",
} as CSSProperties;

type VendorProps = ComponentProps<typeof VendorStepper>;

export function Stepper({ className, style, children, nextDisabled, nextLoading, nextButtonProps, backButtonProps, frame = true, ...props }: Omit<VendorProps, "theme" | "accentColor" | "width"> & {
  children: ReactNode;
  nextDisabled?: boolean;
  nextLoading?: boolean;
  width?: number | string;
}) {
  const { theme } = useTheme(false);
  return (
    <VendorStepper
      {...props}
      theme={theme}
      frame={frame}
      radius={10}
      width={props.width ?? "100%"}
      className={cn("font-sans", className)}
      style={{ ...TOKENS, ...style }}
      backButtonText={props.backButtonText ?? "Back"}
      nextButtonText={props.nextButtonText ?? "Continue"}
      completeButtonText={props.completeButtonText ?? "Finish"}
      nextButtonProps={{ ...nextButtonProps, disabled: nextDisabled || nextLoading || nextButtonProps?.disabled, "aria-busy": nextLoading || undefined }}
      backButtonProps={{ ...backButtonProps, disabled: nextLoading || backButtonProps?.disabled }}
    >
      {children}
    </VendorStepper>
  );
}

/** A plain step header used inside a Step pane: number word, title, one line. */
export function StepTitle({ title, text }: { title: string; text?: ReactNode }) {
  return (
    <div className="mb-4">
      <h2 className="text-lg">{title}</h2>
      {text ? <p className="mt-1 text-sm text-muted-foreground">{text}</p> : null}
    </div>
  );
}
