/** A bounded molecular orbit, shown only while real work is pending. */
export function MoleculeLoader({ size = 40, className = "" }: { size?: number; className?: string }) {
  return <svg className={`cs-molecule-loader ${className}`} width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true">
    <circle className="cs-molecule-loader__track" cx="32" cy="32" r="23" stroke="currentColor" strokeWidth="1.5" opacity=".12"/>
    <path className="cs-molecule-loader__bond" d="m16 39 16-18 17 19M32 21v28" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"/>
    <circle cx="32" cy="21" r="7" fill="currentColor"/><circle cx="16" cy="39" r="5" fill="var(--art-teal)"/><circle cx="49" cy="40" r="5" fill="var(--art-teal)"/><circle cx="32" cy="49" r="3.5" fill="currentColor"/>
    <g className="cs-molecule-loader__orbit"><circle cx="32" cy="9" r="3.5" fill="currentColor"/><path d="M32 9a23 23 0 0 1 23 23" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></g>
  </svg>;
}
