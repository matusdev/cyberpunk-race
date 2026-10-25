/*
 * Line icons (24 × 24 viewBox, stroke = currentColor).
 */
const P: Record<string, string> = {
  flag: '<path d="M5 21V4"/><path d="M5 4h12l-2 4 2 4H5"/><path d="M9 4v8M13 4v8M5 8h12" opacity=".5"/>',
  garage: '<path d="M3 21V9l9-5 9 5v12"/><path d="M7 21v-8h10v8"/><path d="M7 16h10M7 18.5h10"/>',
  trophy: '<path d="M8 4h8v5a4 4 0 0 1-8 0z"/><path d="M8 6H4a3 3 0 0 0 4 4M16 6h4a3 3 0 0 1-4 4"/><path d="M12 13v4M8 21h8M9 17h6"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1L7 17M17 7l2.1-2.1"/>',
  pad: '<path d="M6 8h12a4 4 0 0 1 4 4v1a4 4 0 0 1-7 2.6L14 15h-4l-1 .6A4 4 0 0 1 2 13v-1a4 4 0 0 1 4-4z"/><path d="M7 11v3M5.5 12.5h3"/><circle cx="16.5" cy="11.5" r=".8"/><circle cx="18.5" cy="13.5" r=".8"/>',
  wrench: '<path d="M14.5 6.5a4 4 0 0 0-5.3 5.3L3 18l3 3 6.2-6.2a4 4 0 0 0 5.3-5.3l-2.6 2.6-2.4-.6-.6-2.4z"/>',
  car: '<path d="M3 15l2-5c.4-1 1.2-1.5 2.2-1.5h9.6c1 0 1.8.5 2.2 1.5l2 5v3H3z"/><circle cx="7" cy="18" r="1.6"/><circle cx="17" cy="18" r="1.6"/><path d="M6 10.5h12"/>',
  map: '<path d="M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2z"/><path d="M9 4v14M15 6v14"/>',
  paint: '<path d="M19 3l2 2-9 9-3 1 1-3z"/><path d="M8 15c-3 0-4 2-4 4 0 1-1 2-1 2 3 0 6-1 6-4"/>',
  bolt: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
  power: '<path d="M12 3v8"/><path d="M6.3 6.8a8 8 0 1 0 11.4 0"/>',
  back: '<path d="M15 5l-7 7 7 7"/>'
};

export function icon(name: string) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 24 24');
  s.setAttribute('class', 'ic');
  s.innerHTML = P[name] ?? '';
  return s as unknown as HTMLElement;
}
