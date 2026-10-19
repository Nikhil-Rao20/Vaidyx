// Six small illustrations for "Safe by design", drawn in SVG from the site's tokens so they follow the theme. Each plays its
// short sequence when it appears (the panel remounts when the principle changes).
import { motion, useReducedMotion } from "motion/react";

const FG = "var(--l-fg)", FG2 = "var(--l-fg-2)", FG3 = "var(--l-fg-3)", S = "var(--l-surface)", S2 = "var(--l-surface-2)", L = "var(--l-line)", L2 = "var(--l-line-2)", ACC = "var(--l-accent)";
const E: [number, number, number, number] = [0.22, 1, 0.36, 1];
const CT = "/static/tb-nik/brand/art/ct-chest.png";

function Frame({ children, label }: { children: React.ReactNode; label: string }) {
  return <svg viewBox="0 0 400 260" className="h-auto w-full" role="img" aria-label={label} style={{ fontFamily: "inherit" }}>{children}</svg>;
}
function Chip({ x, y, w, text, bg, fg }: { x: number; y: number; w: number; text: string; bg: string; fg: string }) {
  return (<g><rect x={x} y={y} width={w} height={22} rx={11} fill={bg} /><text x={x + w / 2} y={y + 15} textAnchor="middle" fontSize={11.5} fontWeight={600} fill={fg}>{text}</text></g>);
}

export function PeopleDecide() {
  const r = useReducedMotion();
  const lines = ["Invasive carcinoma, no special type, Nottingham grade 2.", "ER positive (80 %), PR positive (60 %); HER2 2+, FISH advised.", "CT chest and abdomen: no distant disease reported.", "Staging as recorded: cT3 cN1 cM0."];
  return (
    <Frame label="A summary stays a draft until a doctor has reviewed and signed it">
      <rect x={40} y={28} width={320} height={204} rx={14} fill={S} stroke={L} />
      <text x={60} y={54} fontSize={12.5} fontWeight={600} fill={FG}>Case summary</text>
      <text x={60} y={69} fontSize={9} fill={FG3}>Lakshmi R., 58 F · UHID VXH/2026/000123 · synthetic</text>
      {lines.map((t, i) => <text key={t} x={60} y={92 + i * 17} fontSize={9.6} fill={FG2}>{t}</text>)}
      <motion.g initial={{ opacity: 1 }} animate={{ opacity: r ? 0 : [1, 1, 0] }} transition={{ duration: 1.6, times: [0, 0.8, 1] }}>
        <Chip x={276} y={40} w={64} text="Draft" bg={S2} fg={FG2} />
      </motion.g>
      <motion.g initial={{ opacity: r ? 1 : 0, scale: r ? 1 : 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: r ? 0 : 1.5, duration: 0.5, ease: E }} style={{ transformOrigin: "300px 51px" }}>
        <Chip x={262} y={40} w={78} text="Reviewed" bg="var(--l-ok-bg)" fg="var(--l-ok)" />
      </motion.g>
      <line x1={60} y1={168} x2={340} y2={168} stroke={L} />
      <motion.text x={62} y={208} fontSize={30} fill={ACC} style={{ fontFamily: "var(--hand)" }} initial={{ opacity: r ? 1 : 0 }} animate={{ opacity: 1 }} transition={{ delay: r ? 0 : 1.9, duration: 0.9 }}>Dr L. Rao</motion.text>
      <motion.path d="M 62 214 C 110 206, 150 220, 196 210" fill="none" stroke={ACC} strokeWidth={1.4} strokeLinecap="round" initial={{ pathLength: r ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ delay: r ? 0 : 2.2, duration: 0.8, ease: E }} />
      <text x={340} y={190} textAnchor="end" fontSize={9.5} fontWeight={600} fill={FG}>Dr L. Rao, Breast Surgery</text>
      <text x={340} y={204} textAnchor="end" fontSize={9} fill={FG3}>Reviewed 22 Oct 2026, 14:33</text>
    </Frame>
  );
}

export function SourcesFirst() {
  const r = useReducedMotion();
  const rows = ["Specimen: core needle biopsy, left breast, 2 o'clock.", "Microscopy: invasive carcinoma of no special type.", "Tumour size on core: 2.8 cm in the largest dimension.", "Nottingham grade: 2 (tubules 3, pleomorphism 2, mitoses 1).", "ER: positive, 80 % of tumour cells, strong intensity."];
  return (
    <Frame label="A value is shown with the exact line of the report it came from">
      <rect x={28} y={70} width={132} height={96} rx={12} fill={S} stroke={L} />
      <text x={44} y={92} fontSize={8.5} fill={FG3} letterSpacing={1}>TUMOUR SIZE</text>
      <text x={44} y={122} fontSize={23} fontWeight={600} fill={FG}>2.8 cm</text>
      <Chip x={44} y={134} w={62} text="verified" bg="var(--l-ok-bg)" fg="var(--l-ok)" />
      <rect x={194} y={30} width={178} height={200} rx={12} fill={S} stroke={L} />
      <text x={208} y={50} fontSize={10} fontWeight={600} fill={FG}>Histopathology report</text>
      <text x={208} y={62} fontSize={7.5} fill={FG3}>Lakshmi R. · 20 Sep 2026 · synthetic</text>
      <line x1={208} y1={70} x2={358} y2={70} stroke={L} />
      {rows.map((t, i) => (
        <g key={t}>
          {i === 2 ? <motion.rect x={203} y={79 + i * 26} width={160} height={21} rx={5} fill="var(--l-highlight)" initial={{ opacity: r ? 1 : 0 }} animate={{ opacity: 1 }} transition={{ delay: r ? 0 : 1.2, duration: 0.5 }} /> : null}
          <foreignObject x={208} y={80 + i * 26} width={152} height={24}>
            <p style={{ fontSize: 7.4, lineHeight: 1.25, color: i === 2 ? "var(--l-fg)" : "var(--l-fg-2)", fontWeight: i === 2 ? 600 : 400, margin: 0 }}>{t}</p>
          </foreignObject>
        </g>
      ))}
      <motion.path d="M 160 118 C 180 118, 180 142, 203 142" fill="none" stroke="var(--violet)" strokeWidth={2} strokeLinecap="round" initial={{ pathLength: r ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ delay: r ? 0 : 0.4, duration: 0.9, ease: E }} />
      <motion.circle cx={203} cy={142} r={3.5} fill="var(--violet)" initial={{ opacity: r ? 1 : 0 }} animate={{ opacity: 1 }} transition={{ delay: r ? 0 : 1.2 }} />
      <text x={94} y={190} textAnchor="middle" fontSize={8.5} fill={FG3}>one click opens the line</text>
    </Frame>
  );
}

export function ScansForDoctors() {
  const r = useReducedMotion();
  return (
    <Frame label="A CT slice shown to doctors on a monitor; no model reads it">
      <rect x={78} y={26} width={244} height={158} rx={12} fill="#0f1720" />
      <motion.image href={CT} x={132} y={32} width={136} height={136} preserveAspectRatio="xMidYMid slice" initial={{ opacity: r ? 1 : 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.9, delay: 0.2 }} />
      <text x={90} y={44} fontSize={8.5} fill="rgba(255,255,255,0.7)">CT chest · axial · PACS</text>
      <text x={90} y={176} fontSize={7.5} fill="rgba(255,255,255,0.45)">TCGA-LUAD, The Cancer Imaging Archive, CC BY 3.0</text>
      <rect x={186} y={184} width={28} height={10} fill={L2} /><rect x={160} y={194} width={80} height={6} rx={3} fill={L2} />
      {[["LR", 118], ["IK", 158], ["TJ", 198]].map(([ini, x], i) => (
        <motion.g key={ini} initial={{ opacity: r ? 1 : 0, y: r ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 + i * 0.15, duration: 0.5 }}>
          <circle cx={Number(x)} cy={230} r={14} fill={["#0b4e74", "#5b3fc4", "#01b4c2"][i]} />
          <text x={Number(x)} y={234} textAnchor="middle" fontSize={9.5} fontWeight={600} fill="#fff">{ini}</text>
        </motion.g>
      ))}
      <text x={226} y={228} fontSize={11.5} fontWeight={600} fill={FG}>Viewed by doctors</text>
      <text x={226} y={243} fontSize={10} fill={FG3}>No model reads the image</text>
    </Frame>
  );
}

export function InsideHospital() {
  const r = useReducedMotion();
  return (
    <Frame label="Runs on the hospital's own server; records stay on site">
      <motion.rect x={40} y={30} width={320} height={204} rx={26} fill="none" stroke={ACC} strokeWidth={1.5} strokeDasharray="6 6" initial={{ pathLength: r ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.4, ease: E }} />
      <rect x={118} y={86} width={164} height={118} rx={10} fill={S} stroke={L} />
      {[0, 1, 2].map((c) => [0, 1].map((rw) => <rect key={`${c}${rw}`} x={136 + c * 34} y={104 + rw * 30} width={20} height={16} rx={3} fill="var(--l-accent-bg)" />))}
      <rect x={236} y={128} width={30} height={60} rx={6} fill="#0f1720" />
      {[140, 154, 168].map((y, i) => <motion.circle key={y} cx={251} cy={y} r={2.5} fill="#6fd19a" animate={r ? undefined : { opacity: [1, 0.3, 1] }} transition={{ duration: 1.6, delay: i * 0.3, repeat: Infinity }} />)}
      <rect x={190} y={62} width={20} height={20} rx={5} fill={ACC} /><rect x={198.5} y={66} width={3} height={12} fill="#fff" /><rect x={194} y={70.5} width={12} height={3} fill="#fff" />
      <g>
        <rect x={40} y={30} width={96} height={24} rx={12} fill={S} stroke={L} />
        <rect x={54} y={39} width={9} height={8} rx={2} fill={ACC} /><path d="M 55.5 39 v -3 a 3 3 0 0 1 6 0 v 3" fill="none" stroke={ACC} strokeWidth={1.6} />
        <text x={70} y={46} fontSize={11} fontWeight={600} fill={FG}>On-site</text>
      </g>
      <text x={200} y={226} textAnchor="middle" fontSize={11} fill={FG3}>Hospital network</text>
    </Frame>
  );
}

export function IndiaFirst() {
  const r = useReducedMotion();
  const rows = ["NCG guidelines", "ICMR cancer registry", "PM-JAY", "International sources"];
  return (
    <Frame label="NCG, ICMR and PM-JAY come before international sources">
      {rows.map((t, i) => {
        const y = 40 + i * 50;
        const last = i === rows.length - 1;
        return (
          <motion.g key={t} initial={{ opacity: r ? 1 : 0, x: r ? 0 : -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.12, duration: 0.5, ease: E }}>
            <rect x={40} y={y} width={320} height={38} rx={12} fill={last ? "none" : S} stroke={last ? L2 : L} strokeDasharray={last ? "5 5" : undefined} />
            <circle cx={64} cy={y + 19} r={11} fill={last ? S2 : "var(--l-accent-bg)"} />
            <text x={64} y={y + 23} textAnchor="middle" fontSize={11} fontWeight={700} fill={last ? FG3 : ACC}>{i + 1}</text>
            <text x={86} y={y + 23.5} fontSize={13} fontWeight={last ? 500 : 600} fill={last ? FG3 : FG}>{t}</text>
          </motion.g>
        );
      })}
      <motion.rect x={40} y={40} width={320} height={38} rx={12} fill="none" stroke={ACC} strokeWidth={2} animate={r ? undefined : { y: [40, 90, 140, 140, 40] }} transition={{ duration: 6, times: [0, 0.3, 0.6, 0.85, 1], repeat: Infinity, ease: "easeInOut" }} />
      <text x={200} y={246} textAnchor="middle" fontSize={11} fill={FG3}>Indian identifiers, names, units and dates</text>
    </Frame>
  );
}

export function EverythingLogged() {
  const r = useReducedMotion();
  const rows = [["14:32", "Decision recorded", "Dr L. Rao"], ["14:33", "Summary reviewed", "Dr L. Rao"], ["14:40", "Minutes exported", "P. Nair"], ["14:41", "Board deck downloaded", "P. Nair"]];
  return (
    <Frame label="Every AI step and user action is recorded with who and when">
      <rect x={40} y={36} width={320} height={190} rx={16} fill={S} stroke={L} />
      <text x={60} y={62} fontSize={13} fontWeight={600} fill={FG}>Audit log</text>
      <circle cx={338} cy={57} r={8} fill="none" stroke={ACC} strokeWidth={1.6} /><path d="M 338 52 v 5 l 3 2" fill="none" stroke={ACC} strokeWidth={1.6} strokeLinecap="round" />
      <line x1={60} y1={74} x2={340} y2={74} stroke={L} />
      {rows.map(([at, what, who], i) => (
        <motion.g key={at} initial={{ opacity: r ? 1 : 0, y: r ? 0 : 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 + i * 0.35, duration: 0.45, ease: E }}>
          <text x={60} y={100 + i * 32} fontSize={11.5} fill={FG3}>{at}</text>
          <text x={104} y={100 + i * 32} fontSize={12.5} fontWeight={500} fill={FG}>{what}</text>
          <text x={340} y={100 + i * 32} textAnchor="end" fontSize={11.5} fill={FG2}>{who}</text>
        </motion.g>
      ))}
    </Frame>
  );
}

export const ART: Record<string, () => React.JSX.Element> = { people: PeopleDecide, sources: SourcesFirst, scans: ScansForDoctors, onsite: InsideHospital, india: IndiaFirst, audit: EverythingLogged };
