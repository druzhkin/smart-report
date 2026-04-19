// v4 Icon set — minimal hand-drawn SVGs ported from design prototype
// Each is a functional component accepting optional SVG props.

import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

export const Icons = {
  arrowRight: (props: IconProps = {}) => (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...props}>
      <path d="M1 7h12M8 2l5 5-5 5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="square" />
    </svg>
  ),
  arrowLeft: (props: IconProps = {}) => (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...props}>
      <path d="M13 7H1M6 2L1 7l5 5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="square" />
    </svg>
  ),
  copy: (props: IconProps = {}) => (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...props}>
      <rect x="3" y="3" width="8" height="9" stroke="currentColor" strokeWidth="1.1" />
      <path d="M5 3V1h8v9h-2" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  ),
  check: (props: IconProps = {}) => (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...props}>
      <path d="M2 7.5l3.5 3L12 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="square" strokeLinejoin="miter" />
    </svg>
  ),
  x: (props: IconProps = {}) => (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" {...props}>
      <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  ),
  chevronDown: (props: IconProps = {}) => (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" {...props}>
      <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  ),
  download: (props: IconProps = {}) => (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...props}>
      <path d="M7 1v9M3 6l4 4 4-4M2 13h10" stroke="currentColor" strokeWidth="1.2" strokeLinecap="square" />
    </svg>
  ),
  upload: (props: IconProps = {}) => (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" {...props}>
      <path d="M9 13V2M4 7l5-5 5 5M2 16h14" stroke="currentColor" strokeWidth="1.1" strokeLinecap="square" />
    </svg>
  ),
  file: (props: IconProps = {}) => (
    <svg width="14" height="16" viewBox="0 0 14 16" fill="none" {...props}>
      <path d="M2 1h7l4 4v10H2V1z" stroke="currentColor" strokeWidth="1.1" fill="none" />
      <path d="M9 1v4h4" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  ),
  refresh: (props: IconProps = {}) => (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...props}>
      <path d="M1 3v4h4M13 11V7H9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="square" />
      <path d="M2.5 7a4.5 4.5 0 018-2.5L13 7M1 7l2.5 2.5A4.5 4.5 0 0011.5 7" stroke="currentColor" strokeWidth="1.2" fill="none" />
    </svg>
  ),
  plus: (props: IconProps = {}) => (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" {...props}>
      <path d="M6 1v10M1 6h10" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  ),
  dot: (props: IconProps = {}) => (
    <svg width="6" height="6" viewBox="0 0 6 6" {...props}>
      <circle cx="3" cy="3" r="3" fill="currentColor" />
    </svg>
  ),
};

export default Icons;
