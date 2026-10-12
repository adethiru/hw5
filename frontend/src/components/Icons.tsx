// Small inline SVG icon set (no icon library needed).
type P = { size?: number; className?: string };
const base = (size = 16) => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
  strokeWidth: 1.9, strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
});

export const IconBag = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M6 7h12l-1 13H7L6 7Z" /><path d="M9 7a3 3 0 0 1 6 0" /></svg>
);
export const IconHome = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M3 11 12 4l9 7" /><path d="M5 10v10h14V10" /><path d="M10 20v-6h4v6" /></svg>
);
export const IconTag = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M3 12V4h8l10 10-8 8L3 12Z" /><circle cx="7.5" cy="8.5" r="1.5" /></svg>
);
export const IconPlay = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M7 5v14l12-7L7 5Z" fill="currentColor" /></svg>
);
export const IconRefresh = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M20 12a8 8 0 1 1-2.3-5.7" /><path d="M20 4v5h-5" /></svg>
);
export const IconCheck = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="m5 12 5 5 9-10" /></svg>
);
export const IconX = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M6 6l12 12M18 6 6 18" /></svg>
);
export const IconArrow = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></svg>
);
export const IconWrench = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M14.5 6.5a4 4 0 0 0 5 5L21 13l-8 8-3-3 8-8 1.5 1.5" /><path d="M14.5 6.5 9 1 7 3l5.5 5.5" /></svg>
);
export const IconWallet = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><rect x="3" y="6" width="18" height="13" rx="2.5" /><path d="M16 12.5h2" /><path d="M3 9h18" /></svg>
);
export const IconMail = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></svg>
);
export const IconShield = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6l-8-3Z" /><path d="m9 12 2 2 4-4" /></svg>
);
export const IconSpark = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" /></svg>
);

export const ticketIcon = (type: string, size = 18) =>
  type === "customer_order" ? <IconBag size={size} /> : type === "rent_notice" ? <IconHome size={size} /> : type === "price_override" ? <IconTag size={size} /> : <IconSpark size={size} />;
