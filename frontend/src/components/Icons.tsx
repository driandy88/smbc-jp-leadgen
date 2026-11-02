export const Logo = ({ w = 40, h = 36 }: { w?: number; h?: number }) => (
  <svg width={w} height={h} viewBox="0 0 40 36" aria-hidden="true">
    <path d="M26.2 24.6 Q21 27.6 16.1 30.4 Q10.9 27.4 5.7 24.4 Q5.8 18.4 5.6 12.3 Q10.8 9.3 16 6.3 Q21.2 9.4 26.3 12.4 L26.4 17.6 Q26.5 21 30 21 L34.6 21" fill="none" stroke="#1E1E1C" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="36.4" cy="21" r="2.6" fill="#C8442B" stroke="#1E1E1C" strokeWidth="1" />
  </svg>
);

export const Check = () => (
  <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
    <path d="M1.6 5.4 Q3 6.6 4 7.9 Q6 4.6 8.6 2" fill="none" stroke="#F3F0E8" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);

export const Box = ({ on }: { on: boolean }) => <span className="box">{on && <Check />}</span>;

export const Close = ({ color = "#F3F0E8" }: { color?: string }) => (
  <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
    <path d="M1.5 1.6 Q5 5.2 8.5 8.4 M8.4 1.5 Q5 4.9 1.6 8.5" stroke={color} strokeWidth="1.2" fill="none" strokeLinecap="round" />
  </svg>
);

export const Arrow = () => (
  <svg width="22" height="10" viewBox="0 0 22 10" aria-hidden="true">
    <path d="M1 5.2 Q10 4.7 20 5 M15.8 1.2 Q18.4 3.4 20.4 5 Q18.2 6.8 15.9 8.9" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
  </svg>
);

export const Chevron = ({ open }: { open: boolean }) => (
  <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" style={{ transform: open ? "none" : "rotate(-90deg)", transition: "transform .2s ease-out" }}>
    <path d="M2.5 4.2 Q4.4 6.2 6 8 Q7.7 6.1 9.6 4.1" fill="none" stroke="#1E1E1C" strokeWidth="1.3" strokeLinecap="round" />
  </svg>
);

export const Squiggle = ({ w = 64 }: { w?: number }) => (
  <svg width={w} height="18" viewBox="0 0 64 18" aria-hidden="true" preserveAspectRatio="none">
    <path className="hx-stroke" pathLength={1} d="M2 11 Q12 3 22 9 T42 9 T62 7" fill="none" stroke="#1E1E1C" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

export const Done = () => (
  <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
    <path d="M7 15.6 Q10.4 18.4 12.6 21 Q17.4 13.6 23.6 8.4" className="hx-draw" pathLength={1} fill="none" stroke="#5E7D4A" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

export const Lock = ({ open = false }: { open?: boolean }) => (
  <svg width="14" height="16" viewBox="0 0 16 18" aria-hidden="true">
    <path d={open ? "M3.4 8.2 Q3.2 4.9 3.6 3.9 Q5 1.4 8 1.4 Q10.6 1.5 11.8 3.2" : "M3.4 8.2 Q3.2 4.9 3.6 3.9 Q5 1.4 8 1.4 Q11 1.5 12.2 3.8 Q12.6 5.2 12.5 8.1"} fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    <path d="M2 8.3 L14.1 8.1 Q14.4 12.6 14 16.4 L2.1 16.6 Q1.8 12.4 2 8.3 Z M8 11.3 L8.1 13.7" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

// A flat-top hexagon for the area tiles
export const HEX_TILE = "M-14 -21 L14 -21 L28 0 L14 21 L-14 21 L-28 0 Z";
