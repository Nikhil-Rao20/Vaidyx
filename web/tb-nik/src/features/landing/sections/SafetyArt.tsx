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
  const enter = (delay: number) => ({ initial: r ? false : { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 }, transition: { delay: r ? 0 : delay, duration: 0.55, ease: E } });
  return (
    <Frame label="The room display in a meeting: the slide, the report and the CT image, all presented from the Case File">
      <defs><clipPath id="l-art-ct"><rect x={244} y={58} width={92} height={92} rx={6} /></clipPath></defs>
      {/* the room display */}
      <rect x={52} y={22} width={296} height={178} rx={12} fill="#0f1720" />
      <rect x={52} y={22} width={296} height={22} rx={12} fill="#18222e" /><rect x={52} y={34} width={296} height={10} fill="#18222e" />
      <text x={68} y={37} fontSize={8.5} fontWeight={600} fill="#fff">Presentation</text>
      <rect x={68} y={40} width={50} height={1.5} fill="var(--cyan)" />
      <text x={134} y={37} fontSize={8.5} fill="rgba(255,255,255,0.55)">Report</text>
      <text x={172} y={37} fontSize={8.5} fill="rgba(255,255,255,0.55)">Images</text>
      <text x={340} y={37} textAnchor="end" fontSize={7.5} fill="rgba(255,255,255,0.45)">Case File 4 of 9</text>
      {/* the CT image, at the back on the right */}
      <motion.g {...enter(1.1)}>
        <rect x={244} y={58} width={92} height={92} rx={6} fill="#000" />
        <image href={CT} x={244} y={58} width={92} height={92} preserveAspectRatio="xMidYMid slice" clipPath="url(#l-art-ct)" />
        <text x={250} y={68} fontSize={6.5} fill="rgba(255,255,255,0.75)">CT chest · PACS</text>
      </motion.g>
      {/* the report, in the middle */}
      <motion.g {...enter(0.7)}>
        <rect x={176} y={64} width={92} height={118} rx={6} fill="#fff" stroke={L2} />
        <rect x={196} y={70} width={22} height={10} rx={3} fill="#b2362b" /><text x={207} y={77.5} textAnchor="middle" fontSize={6.5} fontWeight={700} fill="#fff">PDF</text>
        <text x={222} y={78} fontSize={6.5} fontWeight={600} fill="#121a24">Report</text>
        <text x={196} y={92} fontSize={6.5} fontWeight={600} fill="#121a24">Histopathology</text>
        {[100, 108, 116, 124, 132, 140, 148, 156, 164, 172].map((y, i) => <rect key={y} x={196} y={y} width={[64, 58, 66, 52, 62, 48, 60, 54, 44, 50][i]} height={3.5} rx={1.75} fill={i === 3 ? "#01cbd3" : "#e2e8ef"} />)}
      </motion.g>
      {/* the slide, in front on the left */}
      <motion.g {...enter(0.25)}>
        <rect x={64} y={56} width={126} height={84} rx={6} fill="#fff" stroke={L2} />
        <rect x={64} y={56} width={126} height={11} rx={6} fill="#00183c" /><rect x={64} y={62} width={126} height={5} fill="#00183c" />
        <text x={70} y={64} fontSize={5.5} fill="#fff">Vaidyx Demo Hospital · Tumour Board</text>
        <text x={70} y={79} fontSize={7} fontWeight={600} fill="#121a24">Lakshmi R., 58 F · Breast cancer</text>
        {[88, 96, 104, 112].map((y, i) => <g key={y}><circle cx={73} cy={y - 1.5} r={1.4} fill="#01b4c2" /><rect x={77} y={y - 3.5} width={[52, 44, 56, 38][i]} height={3.5} rx={1.75} fill="#e2e8ef" /></g>)}
        <rect x={134} y={84} width={52} height={24} rx={3} fill="#f7f9fc" stroke="#e2e8ef" />
        <text x={138} y={92} fontSize={4.6} fontWeight={600} fill="#0a6a86" letterSpacing={0.4}>QUESTION FOR THE BOARD</text>
        <rect x={138} y={96} width={42} height={3} rx={1.5} fill="#e2e8ef" /><rect x={138} y={101} width={30} height={3} rx={1.5} fill="#e2e8ef" />
        {[["cT3", 134], ["cN1", 152], ["cM0", 170]].map(([t, x]) => <g key={t}><rect x={Number(x)} y={112} width={16} height={12} rx={2} fill="#fff" stroke="#e2e8ef" /><text x={Number(x) + 8} y={120.5} textAnchor="middle" fontSize={6} fontWeight={600} fill="#121a24">{t}</text></g>)}
        <text x={70} y={133} fontSize={5} fill="#5f6b78">Every value verified against its source</text>
      </motion.g>
      <rect x={186} y={200} width={28} height={8} fill={L2} /><rect x={160} y={208} width={80} height={5} rx={2.5} fill={L2} />
      {/* what is on the display, named */}
      {[["Slide", 86, 0.25], ["Report, PDF", 170, 0.7], ["CT image", 262, 1.1]].map(([t, x, d]) => (
        <motion.g key={String(t)} {...enter(Number(d) + 0.15)}>
          <rect x={Number(x) - 4} y={222} width={String(t).length * 5.6 + 14} height={16} rx={8} fill={S} stroke={L} />
          <circle cx={Number(x) + 4} cy={230} r={2.5} fill={ACC} />
          <text x={Number(x) + 11} y={233.5} fontSize={8.5} fontWeight={600} fill={FG}>{t}</text>
        </motion.g>
      ))}
      <text x={200} y={254} textAnchor="middle" fontSize={9} fill={FG3}>Presented from the Case File · viewed by doctors · no model reads the images</text>
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
