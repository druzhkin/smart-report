// Smart Report v.IV — shared types for the chat workspace

export type Phase =
  | "start"
  | "prompt"
  | "upload"
  | "critique"
  | "topup"
  | "final"
  | "done";

export type Role = "system" | "user";
export type MsgKind = "text" | "thinking" | "ref" | "cta" | "divider";
export type RefKind = "prompt" | "upload" | "critique" | "report" | "topup";

export interface ChatMessage {
  id: string;
  role: Role;
  kind: MsgKind;
  content?: string;
  refKind?: RefKind;
  title?: string;
  subtitle?: string;
  accent?: boolean;
  traces?: string[];
  onDone?: () => void;
  primary?: string;
  secondary?: string;
  action?: string;
  secondaryAction?: string;
}

export interface Session {
  id: string;
  title: string;
  date: string;
  phase: "active" | "done";
  cost: string;
  current?: boolean;
}

export interface Project {
  id: string;
  name: string;
  color: "orange" | "blue" | "green" | "red" | "ink";
  client: string;
  sessions: Session[];
}

export interface Artifact {
  kind: "prompt" | "upload" | "upload-stage" | "critique" | "topup" | "report";
  // Real API data payload (present when connected to backend)
  data?: unknown;
}

export interface PromptSection {
  id: string;
  title: string;
  body?: string;
  bullets?: string[];
}

export interface PromptMeta {
  words: number;
  recommendation: string;
  reasoning: string;
}

export interface WaitingLogEntry {
  t: string;
  msg: string;
  cost: number;
}

export interface UploadedReport {
  name: string;
  size: string;
  words: number;
  date: string;
  status: string;
}

export interface CritiqueAgreement {
  claim: string;
  sources: number;
  confidence: string;
}

export interface CritiqueContradiction {
  id: string;
  topic: string;
  a: { src: string; body: string };
  b: { src: string; body: string };
  resolution: string;
}

export interface CritiqueUnverified {
  n: string;
  claim: string;
  source: string;
}

export interface Critique {
  agreements: CritiqueAgreement[];
  contradictions: CritiqueContradiction[];
  gaps: string[];
  unverified: CritiqueUnverified[];
  followupPromt: string;
}

export interface BibliographyEntry {
  n: number;
  title: string;
  date: string;
  type: string;
}

export interface HeadlineItem {
  big: string;
  label: string;
  n: number;
}

export interface RankingItem {
  factor: string;
  weight: number;
  band: string;
}

export interface NarrativeSection {
  heading: string;
  id: string;
  paras: string[];
}

export interface TocItem {
  id: string;
  label: string;
  depth: number;
}

export interface FinalReport {
  title: string;
  subtitle: string;
  toc: TocItem[];
  headline: HeadlineItem[];
  ranking: RankingItem[];
  insights: string[];
  narrative: NarrativeSection[];
  bibliography: BibliographyEntry[];
}

export interface MockData {
  session: {
    id: string;
    createdAt: string;
    question: string;
    cost: number;
    costSeries: number[];
    opusCalls: number;
    wallTime: string;
  };
  promptSections: PromptSection[];
  promptMeta: PromptMeta;
  waitingLog: WaitingLogEntry[];
  uploadedReports: UploadedReport[];
  critique: Critique;
  topUpReport: {
    name: string;
    size: string;
    words: number;
    filled: string[];
    stillOpen: string[];
  };
  finalReport: FinalReport;
}

export interface ToastState {
  text: string;
  action?: {
    label: string;
    run: () => void;
  };
}
