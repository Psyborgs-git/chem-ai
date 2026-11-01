import { useId } from "react";

export type BrandMarkProps = {
  size?: number | string;
  className?: string;
  /** Omit beside the written app name; supply when the mark stands alone. */
  label?: string;
};

/** The molecular C. Keep this geometry in sync with public/brand/chemistry-studio.svg. */
export function BrandMark({ size = 32, className = "", label }: BrandMarkProps) {
  const id = `cs-brand-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  return (
    <svg
      className={`cs-brand-logo ${className}`.trim()}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      role={label ? "img" : undefined}
      aria-label={label || undefined}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <defs>
        <linearGradient id={`${id}-tile`} x1="9" y1="5" x2="55" y2="61" gradientUnits="userSpaceOnUse">
          <stop stopColor="#234562" /><stop offset="1" stopColor="#10283D" />
        </linearGradient>
        <linearGradient id={`${id}-bond`} x1="31" y1="15" x2="31" y2="49" gradientUnits="userSpaceOnUse">
          <stop stopColor="#DFEEFF" /><stop offset=".48" stopColor="#B1D0FF" /><stop offset="1" stopColor="#72D8C3" />
        </linearGradient>
      </defs>
      <rect x="5" y="5" width="54" height="54" rx="12.25" fill={`url(#${id}-tile)`} />
      <rect x="5.5" y="5.5" width="53" height="53" rx="11.75" stroke="#D5EEFF" strokeOpacity=".12" />
      <g className="cs-brand-logo__bonds" strokeLinecap="round" strokeLinejoin="round">
        <path d="m41 21 7 11-7 11" stroke="#72D8C3" strokeWidth="2.25" />
        <path d="m41 21-10-6-12 7v20l12 7 10-6" stroke={`url(#${id}-bond)`} strokeWidth="6.25" />
      </g>
      <circle cx="41" cy="21" r="4.25" fill="#DBEDFF" />
      <circle cx="41" cy="43" r="4.25" fill="#72D8C3" />
      <circle className="cs-brand-logo__atom" cx="48" cy="32" r="3.5" fill="#8CE5D1" />
    </svg>
  );
}
