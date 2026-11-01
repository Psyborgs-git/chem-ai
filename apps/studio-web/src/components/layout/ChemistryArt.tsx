import { useId } from "react";

export type ChemistryArtKind = "molecule" | "research" | "improve" | "match" | "sources" | "experiment";

type ArtPalette = { blue: string; teal: string; paper: string; wash: string };

function Atom({ x, y, r = 12, tone = "blue", palette }: {
  x: number; y: number; r?: number; tone?: "blue" | "teal" | "paper"; palette: ArtPalette;
}) {
  return <g>
    <circle cx={x} cy={y + 2} r={r} fill="var(--art-line)" opacity=".16" stroke="none" />
    <circle cx={x} cy={y} r={r} fill={`url(#${palette[tone]})`} stroke={tone === "paper" ? "var(--art-line)" : "none"} strokeWidth="1.5" />
    <path d={`M${x - r * .43} ${y - r * .3}q${r * .2} ${-r * .3} ${r * .52} ${-r * .25}`} stroke="white" opacity=".55" strokeWidth="2" />
  </g>;
}

function Molecule({ palette }: { palette: ArtPalette }) {
  return <>
    <g className="cs-art__orbit" stroke="var(--art-line)" strokeWidth="1" opacity=".5">
      <ellipse cx="120" cy="83" rx="90" ry="47" transform="rotate(-20 120 83)" strokeDasharray="3 7" />
      <path d="M65 30v10m-5-5h10M202 101v8m-4-4h8" />
    </g>
    <g className="cs-art__subject" stroke="var(--art-line)" strokeWidth="5" strokeLinecap="round">
      <path d="m58 98 52-32 51 28 34-27M110 66l-3-35m3 35-7 61m58-33 14 33" />
      <path d="m62 105 47-28m7-7 39 23" stroke="var(--surface)" opacity=".65" strokeWidth="1.5" />
      <Atom x={58} y={98} r={19} palette={palette} />
      <Atom x={110} y={66} r={24} tone="paper" palette={palette} />
      <Atom x={161} y={94} r={20} tone="teal" palette={palette} />
      <Atom x={195} y={67} r={11} tone="paper" palette={palette} />
      <Atom x={107} y={31} r={10} tone="teal" palette={palette} />
      <Atom x={103} y={127} r={9} tone="paper" palette={palette} />
      <Atom x={175} y={127} r={8} palette={palette} />
      <circle cx="110" cy="66" r="6" fill="var(--art-blue)" stroke="none" opacity=".85" />
    </g>
  </>;
}

function Research({ palette }: { palette: ArtPalette }) {
  return <>
    <g className="cs-art__back" transform="rotate(-7 112 84)">
      <rect x="43" y="32" width="130" height="105" rx="10" fill="var(--art-line)" opacity=".12" stroke="none" />
      <rect x="41" y="28" width="130" height="105" rx="10" fill={`url(#${palette.paper})`} />
      <path d="M55 45h42m-42 8h27M55 116h32m8 0h13" opacity=".4" strokeWidth="2" />
      <path d="m84 68 23-13 23 13v26l-23 13-23-13Z" stroke="var(--art-blue)" strokeWidth="2.5" />
      <path d="m90 72 17-10m17 10v19m-18 9-16-9m40-23 19-11" strokeWidth="2" />
      <circle cx="150" cy="56" r="5" fill="var(--art-teal)" stroke="none" />
    </g>
    <g className="cs-art__subject">
      <path d="m168 110 25 25" stroke="var(--art-blue)" strokeWidth="12" />
      <circle cx="148" cy="89" r="34" fill={`url(#${palette.wash})`} stroke="var(--art-blue)" strokeWidth="5" />
      <path d="M129 75a24 24 0 0 1 18-9" stroke="var(--surface)" strokeWidth="3" opacity=".85" />
      <path d="m129 96 15-19 19 15m-19-15 8 27" stroke="var(--art-teal)" strokeWidth="2.5" />
      <Atom x={129} y={96} r={5} tone="teal" palette={palette} />
      <Atom x={144} y={77} r={7} palette={palette} />
      <Atom x={163} y={92} r={5} tone="teal" palette={palette} />
      <Atom x={152} y={104} r={4} tone="paper" palette={palette} />
    </g>
  </>;
}

function Improve({ palette }: { palette: ArtPalette }) {
  return <>
    <g className="cs-art__back">
      <rect x="33" y="34" width="116" height="99" rx="12" fill={`url(#${palette.paper})`} />
      <path d="M49 54h83M49 77h83M49 100h83" opacity=".5" strokeWidth="2" />
      <circle cx="78" cy="54" r="7" fill={`url(#${palette.blue})`} stroke="none" />
      <circle cx="113" cy="77" r="7" fill={`url(#${palette.teal})`} stroke="none" />
      <circle cx="67" cy="100" r="7" fill={`url(#${palette.blue})`} stroke="none" />
      <path d="M49 117h34m6 0h18" opacity=".3" strokeWidth="2" />
    </g>
    <g className="cs-art__subject">
      <path d="m151 42 34 20v40l-34 20-34-20V62Z" fill={`url(#${palette.wash})`} stroke="var(--art-teal)" strokeWidth="2" />
      <path d="m151 42 1 39 33 21m-33-21-35 21m35-21 33-19" strokeWidth="3" />
      <Atom x={151} y={42} r={10} tone="paper" palette={palette} />
      <Atom x={185} y={62} r={10} palette={palette} />
      <Atom x={152} y={81} r={16} tone="teal" palette={palette} />
      <Atom x={185} y={102} r={11} tone="paper" palette={palette} />
      <Atom x={151} y={122} r={9} palette={palette} />
      <Atom x={117} y={102} r={9} tone="paper" palette={palette} />
    </g>
  </>;
}

function Match({ palette }: { palette: ArtPalette }) {
  return <>
    <g className="cs-art__back" strokeWidth="1.5">
      <rect x="28" y="35" width="80" height="101" rx="12" fill={`url(#${palette.paper})`} />
      <rect x="132" y="23" width="80" height="101" rx="12" fill={`url(#${palette.paper})`} />
      <path d="M43 117h31m-31 6h20M147 105h32m-32 6h20" opacity=".4" strokeWidth="2" />
    </g>
    <g className="cs-art__subject" strokeWidth="3">
      <path d="m48 72 20-12 20 12v24L68 108 48 96Zm104-12 20-12 20 12v24l-20 12-20-12Z" />
      <path d="m53 76 15-9m15 9v16m74-28 15-9m15 9v16" opacity=".55" strokeWidth="1.5" />
      <Atom x={48} y={72} r={6} palette={palette} />
      <Atom x={88} y={96} r={6} tone="teal" palette={palette} />
      <Atom x={152} y={60} r={6} palette={palette} />
      <Atom x={192} y={84} r={6} tone="teal" palette={palette} />
      <circle cx="120" cy="80" r="18" fill={`url(#${palette.paper})`} strokeWidth="2" />
      <path d="M111 76h17m-4-4 4 4-4 4m4 5h-17m4-4-4 4 4 4" stroke="var(--art-blue)" strokeWidth="2" />
    </g>
    <path className="cs-art__orbit" d="M43 28c37-22 120-20 154 1M43 143c41 12 106 13 150-7" strokeDasharray="3 6" opacity=".4" strokeWidth="1.5" />
  </>;
}

function Sources({ palette }: { palette: ArtPalette }) {
  return <>
    <g className="cs-art__back" transform="rotate(-11 92 82)">
      <rect x="43" y="31" width="85" height="110" rx="9" fill={`url(#${palette.wash})`} />
      <path d="M57 49h38m-38 10h51m-51 13h44m-44 11h30m-30 11h48m-48 11h43" opacity=".45" strokeWidth="2" />
    </g>
    <g className="cs-art__subject">
      <rect x="85" y="22" width="90" height="116" rx="9" fill={`url(#${palette.paper})`} />
      <path d="M100 42h35m-35 9h54" stroke="var(--art-blue)" strokeWidth="3" />
      <path d="M100 65h58m-58 10h43m-43 10h53m-53 26h21m-21 9h30" opacity=".45" strokeWidth="2" />
      <rect x="100" y="92" width="52" height="8" rx="3" fill="var(--art-mint)" stroke="none" />
      <circle cx="174" cy="112" r="23" fill={`url(#${palette.teal})`} stroke="var(--surface)" strokeWidth="3" />
      <g transform="rotate(-35 174 112)" stroke="white" strokeWidth="2.5">
        <rect x="162" y="106" width="16" height="12" rx="6" />
        <rect x="171" y="106" width="16" height="12" rx="6" />
      </g>
    </g>
  </>;
}

function Experiment({ palette }: { palette: ArtPalette }) {
  return <>
    <g className="cs-art__back" strokeWidth="2">
      <path d="M43 134h156M57 134V28m-9 0h18m-9 23h40" />
      <rect x="90" y="43" width="18" height="13" rx="4" fill={`url(#${palette.paper})`} />
      <path d="M164 80v44m-8-44h16m-9 44h17m9-44v44m-8-44h16" opacity=".6" />
      <rect x="154" y="117" width="45" height="18" rx="4" fill={`url(#${palette.paper})`} />
    </g>
    <g className="cs-art__subject">
      <path d="M91 29h38m-32 0v38l-29 52a9 9 0 0 0 8 14h68a9 9 0 0 0 8-14l-29-52V29" fill={`url(#${palette.paper})`} strokeWidth="2.5" />
      <path d="M85 97c15-9 29 8 50-1l14 26a5 5 0 0 1-5 8H76a5 5 0 0 1-5-8Z" fill={`url(#${palette.teal})`} stroke="none" />
      <path d="M105 51h12m-12 12h12M130 111h9m-4 10h9" strokeWidth="2" opacity=".55" />
      <path d="M102 77 88 103" stroke="white" strokeWidth="3" opacity=".6" />
      <g className="cs-art__detail" fill="var(--surface)" stroke="none" opacity=".8"><circle cx="103" cy="112" r="3" /><circle cx="117" cy="121" r="4" /><circle cx="119" cy="101" r="2" /></g>
      <g transform="rotate(25 171 46)"><rect x="165" y="23" width="12" height="38" rx="4" fill={`url(#${palette.blue})`} stroke="var(--art-blue)" strokeWidth="1.5" /><path d="M168 62v14l3 6 3-6V62" fill={`url(#${palette.paper})`} strokeWidth="1.5" /><path d="M165 29h12" stroke="white" opacity=".5" strokeWidth="2" /></g>
      <path d="M171 92c-5 6-5 9 0 9s5-3 0-9Z" fill="var(--art-teal)" stroke="none" />
    </g>
  </>;
}

const ILLUSTRATIONS = { molecule: Molecule, research: Research, improve: Improve, match: Match, sources: Sources, experiment: Experiment };

/** Decorative wayfinding only. Actual molecule drawings come from the recorded calculation. */
export function ChemistryArt({ kind, className = "" }: { kind: ChemistryArtKind; className?: string }) {
  const id = `cs-art-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const palette = { blue: `${id}-blue`, teal: `${id}-teal`, paper: `${id}-paper`, wash: `${id}-wash` };
  const Illustration = ILLUSTRATIONS[kind];
  return <svg className={`cs-chemistry-art cs-chemistry-art--${kind} ${className}`.trim()} data-art={kind} viewBox="0 0 240 160" fill="none" aria-hidden="true" focusable="false">
    <defs>
      <linearGradient id={palette.blue} x1="0" y1="0" x2=".8" y2="1"><stop stopColor="var(--art-blue)" /><stop offset="1" stopColor="var(--accent)" /></linearGradient>
      <linearGradient id={palette.teal} x1="0" y1="0" x2=".8" y2="1"><stop stopColor="var(--art-teal)" /><stop offset="1" stopColor="var(--art-teal)" stopOpacity=".78" /></linearGradient>
      <linearGradient id={palette.paper} x1="0" y1="0" x2="1" y2="1"><stop stopColor="var(--surface)" /><stop offset="1" stopColor="var(--surface-raised)" /></linearGradient>
      <linearGradient id={palette.wash} x1="0" y1="0" x2="1" y2="1"><stop stopColor="var(--art-soft)" /><stop offset="1" stopColor="var(--art-mint)" /></linearGradient>
    </defs>
    <path className="cs-art__backdrop" d="M32 52C48 16 98 9 142 16c47 8 77 28 75 66-3 43-43 64-98 61-50-3-109-8-104-45 2-18 8-29 17-46Z" fill={`url(#${palette.wash})`} />
    <g stroke="var(--art-line)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><Illustration palette={palette} /></g>
    <g className="cs-art__spark" fill="var(--art-line)" opacity=".5"><circle cx="29" cy="65" r="2" /><circle cx="211" cy="125" r="2" /><circle cx="199" cy="25" r="2.5" /></g>
  </svg>;
}
