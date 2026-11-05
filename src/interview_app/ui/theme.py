"""Brand, palette tokens, mascot and global CSS.

Palette values are Tailwind CSS colours so they stay consistent and easy to swap: change
ACTIVE_PALETTE (and mirror the four base colours in .streamlit/config.toml).
Everything Streamlit cannot theme natively is styled by CSS below, which targets keyed
containers (`st.container(key="x")` → `.st-key-x`).
"""

from __future__ import annotations

import base64

APP_NAME = "Hoot"
APP_TAGLINE = "AI Interview Prep"

# ---------- palettes (Tailwind names in comments) ----------

PALETTES: dict[str, dict[str, str]] = {
    # Recommended: slate neutrals, indigo→fuchsia hero, warm coral accent (complementary).
    "indigo-coral": {
        "accent": "#F97316",  # orange-500
        "accent_hover": "#EA580C",  # orange-600
        "accent_soft": "#FFEDD5",  # orange-100
        "ink": "#1E293B",  # slate-800
        "muted": "#64748B",  # slate-500
        "border": "#E2E8F0",  # slate-200
        "bg": "#F8FAFC",  # slate-50
        "surface": "#FFFFFF",
        "section": "#EEF2FF",  # indigo-50
        "section_2": "#E0E7FF",  # indigo-100
        "brand": "#4F46E5",  # indigo-600
        "brand_deep": "#312E81",  # indigo-900
        "hero_1": "#312E81",  # indigo-900
        "hero_2": "#6D28D9",  # violet-700
        "hero_3": "#C026D3",  # fuchsia-600
        "hero_4": "#EC4899",  # pink-500
        "welcome_1": "#EEF2FF",  # indigo-50
        "welcome_2": "#F5F3FF",  # violet-50
        "success": "#10B981",  # emerald-500
        "mascot_body_1": "#8B5CF6",  # violet-500
        "mascot_body_2": "#4338CA",  # indigo-700
        "mascot_tuft": "#3730A3",  # indigo-800
        "mascot_belly": "#DDD6FE",  # violet-200
        "mascot_belly_line": "#C4B5FD",  # violet-300
        "mascot_face": "#F8FAFC",  # slate-50
        "mascot_eye": "#0F172A",  # slate-900
        "mascot_beak": "#FBBF24",  # amber-400
    },
    # Alternative: zinc neutrals, grape hero, honey accent.
    "violet-amber": {
        "accent": "#F59E0B",  # amber-500
        "accent_hover": "#D97706",  # amber-600
        "accent_soft": "#FEF3C7",  # amber-100
        "ink": "#27272A",  # zinc-800
        "muted": "#71717A",  # zinc-500
        "border": "#E4E4E7",  # zinc-200
        "bg": "#FAFAFA",  # zinc-50
        "surface": "#FFFFFF",
        "section": "#F5F3FF",  # violet-50
        "section_2": "#EDE9FE",  # violet-100
        "brand": "#7C3AED",  # violet-600
        "brand_deep": "#4C1D95",  # violet-900
        "hero_1": "#4C1D95",  # violet-900
        "hero_2": "#7E22CE",  # purple-700
        "hero_3": "#C026D3",  # fuchsia-600
        "hero_4": "#F472B6",  # pink-400
        "welcome_1": "#F5F3FF",  # violet-50
        "welcome_2": "#FDF4FF",  # fuchsia-50
        "success": "#10B981",
        "mascot_body_1": "#A78BFA",  # violet-400
        "mascot_body_2": "#6D28D9",  # violet-700
        "mascot_tuft": "#5B21B6",  # violet-800
        "mascot_belly": "#EDE9FE",  # violet-100
        "mascot_belly_line": "#C4B5FD",
        "mascot_face": "#FAFAFA",
        "mascot_eye": "#18181B",  # zinc-900
        "mascot_beak": "#FBBF24",
    },
    # Alternative: slate neutrals, teal→cyan hero, rose accent. Least "AI-purple".
    "teal-rose": {
        "accent": "#F43F5E",  # rose-500
        "accent_hover": "#E11D48",  # rose-600
        "accent_soft": "#FFE4E6",  # rose-100
        "ink": "#1E293B",
        "muted": "#64748B",
        "border": "#E2E8F0",
        "bg": "#F8FAFC",
        "surface": "#FFFFFF",
        "section": "#F0FDFA",  # teal-50
        "section_2": "#CCFBF1",  # teal-100
        "brand": "#0D9488",  # teal-600
        "brand_deep": "#134E4A",  # teal-900
        "hero_1": "#134E4A",  # teal-900
        "hero_2": "#0F766E",  # teal-700
        "hero_3": "#0891B2",  # cyan-600
        "hero_4": "#22D3EE",  # cyan-400
        "welcome_1": "#F0FDFA",  # teal-50
        "welcome_2": "#ECFEFF",  # cyan-50
        "success": "#10B981",
        "mascot_body_1": "#2DD4BF",  # teal-400
        "mascot_body_2": "#0F766E",  # teal-700
        "mascot_tuft": "#115E59",  # teal-800
        "mascot_belly": "#CCFBF1",  # teal-100
        "mascot_belly_line": "#99F6E4",  # teal-200
        "mascot_face": "#F8FAFC",
        "mascot_eye": "#0F172A",
        "mascot_beak": "#FBBF24",
    },
}

ACTIVE_PALETTE = "violet-amber"
P = PALETTES[ACTIVE_PALETTE]


def _fill(template: str, values: dict[str, str]) -> str:
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", v)
    return template


# ---------- mascot ----------

_MASCOT = """<svg viewBox="0 0 120 120" width="{{size}}" height="{{size}}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{{name}} mascot">
  <defs>
    <linearGradient id="hoot-body" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{{mascot_body_1}}"/><stop offset="1" stop-color="{{mascot_body_2}}"/>
    </linearGradient>
  </defs>
  <path d="M30 40 L22 12 L48 30 Z" fill="{{mascot_tuft}}"/>
  <path d="M90 40 L98 12 L72 30 Z" fill="{{mascot_tuft}}"/>
  <ellipse cx="60" cy="68" rx="43" ry="45" fill="url(#hoot-body)"/>
  <ellipse cx="60" cy="88" rx="26" ry="20" fill="{{mascot_belly}}"/>
  <path d="M46 84 q7 -6 14 0 q7 -6 14 0" stroke="{{mascot_belly_line}}" stroke-width="3" fill="none" stroke-linecap="round"/>
  <path d="M46 96 q7 -6 14 0 q7 -6 14 0" stroke="{{mascot_belly_line}}" stroke-width="3" fill="none" stroke-linecap="round"/>
  <circle cx="41" cy="56" r="18" fill="{{mascot_face}}"/>
  <circle cx="79" cy="56" r="18" fill="{{mascot_face}}"/>
  <circle cx="41" cy="56" r="15.5" fill="none" stroke="{{accent}}" stroke-width="4.5"/>
  <circle cx="79" cy="56" r="15.5" fill="none" stroke="{{accent}}" stroke-width="4.5"/>
  <path d="M56.5 56 L63.5 56" stroke="{{accent}}" stroke-width="4.5" stroke-linecap="round"/>
  <path d="M25.5 54 L19 50" stroke="{{accent}}" stroke-width="4.5" stroke-linecap="round"/>
  <path d="M94.5 54 L101 50" stroke="{{accent}}" stroke-width="4.5" stroke-linecap="round"/>
  <circle cx="43" cy="57" r="6.5" fill="{{mascot_eye}}"/><circle cx="45.5" cy="54.5" r="2.2" fill="#fff"/>
  <circle cx="81" cy="57" r="6.5" fill="{{mascot_eye}}"/><circle cx="83.5" cy="54.5" r="2.2" fill="#fff"/>
  <path d="M60 64 L53 73 L67 73 Z" fill="{{mascot_beak}}"/>
  <path d="M44 111 l-6 7 M44 111 l0 8 M44 111 l6 7" stroke="{{mascot_beak}}" stroke-width="4" stroke-linecap="round" fill="none"/>
  <path d="M76 111 l-6 7 M76 111 l0 8 M76 111 l6 7" stroke="{{mascot_beak}}" stroke-width="4" stroke-linecap="round" fill="none"/>
</svg>"""


def mascot_svg(size: int = 44, palette: dict[str, str] | None = None) -> str:
    return _fill(_MASCOT, {**(palette or P), "size": str(size), "name": APP_NAME})


def mascot(size: int = 44) -> str:
    """Mascot as an <img> with a data URI: st.html sanitises inline <svg> away, images survive."""
    data = base64.b64encode(mascot_svg(size).encode("utf-8")).decode("ascii")
    return (
        f'<img src="data:image/svg+xml;base64,{data}" width="{size}" height="{size}" '
        f'alt="{APP_NAME} mascot" style="display:block">'
    )


# ---------- CSS ----------

_CSS = """
<style>
:root {
  --accent: {{accent}}; --accent-hover: {{accent_hover}}; --accent-soft: {{accent_soft}};
  --ink: {{ink}}; --muted: {{muted}}; --border: {{border}}; --bg: {{bg}}; --surface: {{surface}};
  --section: {{section}}; --section-2: {{section_2}}; --brand: {{brand}}; --brand-deep: {{brand_deep}};
  --success: {{success}};
  --font: "Plus Jakarta Sans", "Inter", -apple-system, "Segoe UI", sans-serif;
}
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"], button, input, textarea, select {
  font-family: var(--font);
}
.block-container { padding-top: 3.4rem; padding-bottom: 3rem; max-width: 1320px; }
[data-testid="stHeader"] { background: transparent; }
.stAppDeployButton, [data-testid="stMainMenu"] { display: none; }
h1, h2, h3 { letter-spacing: -0.3px; }

/* ---------- sidebar: pinned brand, scrolling rest ---------- */
[data-testid="stSidebar"] { border-right: 1px solid var(--border); }
/* Zero-height sticky header: the collapse chevron stays pinned beside the brand while the
   content scrolls underneath. */
[data-testid="stSidebarHeader"] { position: sticky; top: 0; height: 0; min-height: 0; padding: 0;
  overflow: visible; z-index: 30; background: transparent; }
[data-testid="stSidebarCollapseButton"] { position: absolute; top: 18px; right: 14px;
  opacity: 1 !important; visibility: visible !important; }
[data-testid="stSidebarCollapseButton"] button { opacity: 1 !important; visibility: visible !important;
  color: var(--muted); }
[data-testid="stSidebarHeader"] [data-testid="stLogoSpacer"] { display: none; }
[data-testid="stSidebarCollapseButton"] button { color: var(--muted); }
[data-testid="stSidebarUserContent"] { padding-top: 0; }
/* Streamlit wraps each block in a layout wrapper exactly its own height, so the wrapper
   (not the keyed container) must be the sticky element. */
[data-testid="stSidebar"] [data-testid="stLayoutWrapper"]:has(> .st-key-brand) {
  position: sticky; top: 0; z-index: 20; padding: 16px 0 12px; margin-bottom: 10px; }
/* Full-bleed white band behind the pinned brand (the wrapper itself cannot grow wider). */
[data-testid="stSidebar"] [data-testid="stLayoutWrapper"]:has(> .st-key-brand)::before {
  content: ""; position: absolute; top: 0; bottom: 0; left: -2rem; right: -4rem; z-index: -1;
  background: var(--surface); border-bottom: 1px solid var(--border); }
.hoot-brand { display: flex; align-items: center; gap: 12px; }
.hoot-brand .name { font-size: 26px; font-weight: 800; color: var(--ink); line-height: 1.05; }
.hoot-brand .tag { font-size: 14px; color: var(--muted); margin-top: 2px; }
.hoot-welcome { background: linear-gradient(135deg, {{welcome_1}}, {{welcome_2}}); border-radius: 16px;
  padding: 18px 18px; margin: 4px 0 14px; line-height: 1.6; font-size: 16px; }
.hoot-welcome b { color: var(--accent); }
.hoot-welcome .sub { color: var(--muted); }
.hoot-menu-label { font-size: 12px; letter-spacing: .12em; font-weight: 700; color: var(--muted);
  margin: 10px 0 6px; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a {
  border-radius: 14px; padding: 12px 16px; color: var(--ink); width: 100%; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover { background: var(--section); }
[data-testid="stSidebar"] [data-testid="stPageLink"] a p { font-weight: 600; font-size: 16px; }
.hoot-nav-active { background: var(--accent); color: #fff; font-weight: 700; font-size: 16px;
  border-radius: 14px; padding: 12px 16px; display: flex; gap: 12px; align-items: center;
  box-shadow: 0 8px 18px color-mix(in srgb, var(--accent) 40%, transparent); }
.hoot-usage { background: linear-gradient(135deg, {{hero_2}}, {{hero_4}}); color: #fff; border-radius: 16px;
  padding: 16px 18px; margin-top: 8px; }
.hoot-usage .label { font-size: 12px; opacity: .85; }
.hoot-usage .big { font-size: 22px; font-weight: 800; line-height: 1.2; }
.hoot-usage .row { display: flex; justify-content: space-between; gap: 10px; }
.hoot-usage .small { font-size: 12px; opacity: .9; margin-top: 6px; }
.hoot-signin { text-align: center; margin-top: 12vh; padding: 32px 24px 8px; }
.hoot-signin img { display: block; margin: 0 auto; }
.hoot-signin .name { font-size: 2rem; font-weight: 800; margin-top: 8px; }
.hoot-signin .tag { color: var(--muted); margin-bottom: 16px; }
.hoot-signin p { color: var(--muted); }
.hoot-user { display: flex; align-items: center; gap: 12px; border: 1px solid var(--border);
  border-radius: 16px; padding: 12px 14px; margin-top: 10px; background: var(--surface); }
.hoot-avatar { width: 40px; height: 40px; border-radius: 50%; flex: none; color: #fff;
  background: linear-gradient(135deg, var(--brand), var(--accent)); display: flex; align-items: center;
  justify-content: center; font-weight: 700; }
.hoot-user .n { font-weight: 700; font-size: 15px; }
.hoot-user .e { font-size: 12px; color: var(--muted); }
.hoot-log { font-size: 13px; line-height: 1.4; padding: 6px 0; border-bottom: 1px solid var(--border); }
.hoot-log small { color: var(--muted); }

/* ---------- footer ---------- */
.st-key-footer { margin-top: 56px; padding-top: 14px; border-top: 1px solid var(--border); }
.st-key-footer a p, .st-key-footer a span { font-size: 13px; color: var(--muted); }

/* ---------- hero ---------- */
.st-key-hero { position: relative; overflow: hidden; border-radius: 28px; padding: 44px 46px 38px; color: #fff;
  background:
    radial-gradient(rgba(255,255,255,.10) 1.2px, transparent 1.2px) 0 0 / 22px 22px,
    linear-gradient(100deg, {{hero_1}} 0%, {{hero_2}} 42%, {{hero_3}} 72%, {{hero_4}} 100%);
  box-shadow: 0 20px 50px color-mix(in srgb, {{hero_1}} 28%, transparent); margin-bottom: 26px; }
.hoot-hero h1 { color: #fff; font-size: 40px; font-weight: 800; line-height: 1.1; margin: 0 0 14px; letter-spacing: -0.5px; }
.hoot-hero p { color: rgba(255,255,255,.93); font-size: 17px; line-height: 1.55; margin: 0 0 18px; max-width: 760px; }
.hoot-chip { display: inline-flex; align-items: center; gap: 6px; background: rgba(255,255,255,.14);
  border: 1px solid rgba(255,255,255,.2); padding: 7px 14px; border-radius: 999px; font-size: 14px;
  font-weight: 600; margin: 0 8px 10px 0; color: #fff; }
.st-key-hero_primary button { background: #fff !important; color: var(--brand-deep) !important;
  border: none !important; font-weight: 700; padding: 0.7rem 1.4rem; font-size: 16px;
  box-shadow: 0 10px 26px rgba(0,0,0,.22); }
.st-key-hero_primary button:hover { background: var(--section) !important; }
.st-key-hero_secondary button, .st-key-hero_resume button { background: transparent !important; color: #fff !important;
  border: none !important; font-weight: 700; font-size: 16px; padding: 0.7rem 0.6rem; }
.st-key-hero_secondary button:hover, .st-key-hero_resume button:hover { text-decoration: underline; }
.hoot-chat { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.16);
  border-radius: 22px; padding: 18px; backdrop-filter: blur(4px); }
.hoot-chat .b { background: #fff; color: var(--ink); border-radius: 16px; padding: 12px 16px;
  margin-bottom: 12px; font-size: 15px; line-height: 1.45; }
.hoot-chat .tag { display: inline-block; background: var(--section); color: var(--brand); font-size: 11px;
  font-weight: 700; letter-spacing: .06em; padding: 3px 9px; border-radius: 8px; margin-bottom: 6px; }
.hoot-chat .speak { text-align: right; margin-bottom: 12px; }
.hoot-chat .speak span { display: inline-block; background: linear-gradient(90deg, var(--brand), var(--accent));
  color: #fff; padding: 8px 14px; border-radius: 999px; font-size: 13px; font-weight: 600; }
.hoot-chat .who { display: flex; align-items: center; gap: 8px; font-size: 13px; color: rgba(255,255,255,.9); }
.hoot-chat .av { width: 24px; height: 24px; border-radius: 50%; border: 2px solid #fff; display: inline-block; margin-right: -8px; }

/* ---------- roles section ---------- */
.st-key-roles { background: var(--section); border-radius: 28px; padding: 34px 38px 30px; margin-bottom: 26px; }
.hoot-section h2 { font-size: 36px; font-weight: 800; margin: 0 0 4px; color: var(--ink); letter-spacing: -0.5px; }
.hoot-section h2 span { color: var(--accent); }
.hoot-section p { color: var(--muted); font-size: 17px; margin: 0 0 8px; }
.st-key-roles [data-testid="stTextInput"] input { background: var(--surface); border-radius: 14px; height: 48px; font-size: 15px; }
.st-key-roles [data-testid="stTextInput"] label { display: none; }
[class*="st-key-role_card_"] { background: var(--surface); border: 1px solid var(--border); border-radius: 22px;
  padding: 14px 14px 12px; height: 100%; transition: transform .15s, box-shadow .15s; }
[class*="st-key-role_card_"]:hover { transform: translateY(-2px); box-shadow: 0 12px 28px color-mix(in srgb, var(--brand-deep) 12%, transparent); }
.hoot-role-art { height: 118px; border-radius: 16px; display: flex; align-items: center; justify-content: center;
  font-size: 54px; position: relative; margin-bottom: 10px; }
.hoot-pill { position: absolute; top: 10px; right: 10px; background: #fff; color: var(--ink); font-size: 12px;
  font-weight: 700; padding: 4px 10px; border-radius: 999px; box-shadow: 0 2px 8px rgba(0,0,0,.08); }
.hoot-role-name { font-weight: 700; font-size: 16px; color: var(--ink); margin: 2px 0 2px; }
.hoot-role-topics { font-size: 13px; color: var(--muted); line-height: 1.4; height: 36px; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; margin-bottom: 6px; }
[class*="st-key-role_card_"] .stButton button { border-radius: 12px; font-weight: 700; }

/* ---------- prompt lab ---------- */
.st-key-lab_input { background: var(--surface); border: 1px solid var(--border); border-radius: 22px; padding: 18px 22px; margin-bottom: 10px; }
[class*="st-key-lab_card_"] { background: var(--surface); border: 1px solid var(--border); border-radius: 18px; padding: 12px 14px; height: 100%; }

/* ---------- practice setup ---------- */
.st-key-setup { background: var(--surface); border: 1px solid var(--border); border-radius: 22px; padding: 22px 26px 18px; }
.hoot-step { display: flex; align-items: flex-start; gap: 12px; margin: 14px 0 2px; }
.hoot-step:first-child { margin-top: 0; }
.hoot-step-no { flex: none; width: 28px; height: 28px; border-radius: 999px; background: var(--accent-soft); color: var(--accent);
  font-weight: 800; font-size: 14px; display: flex; align-items: center; justify-content: center; margin-top: 1px; }
.hoot-step h4 { margin: 0; font-size: 18px; font-weight: 700; color: var(--ink); line-height: 1.5; }
.hoot-step p { margin: 0; color: var(--muted); font-size: 14px; }
.st-key-setup [data-testid="stCaptionContainer"] { margin-top: -6px; }

/* ---------- jd analyzer ---------- */
.st-key-jd_input { background: var(--surface); border: 1px solid var(--border); border-radius: 22px; padding: 22px 26px 18px; }
.st-key-jd_input [data-testid="stCaptionContainer"] { margin-top: -6px; }
.st-key-jd_result { background: var(--section); border-radius: 22px; padding: 22px 26px 20px; margin-bottom: 6px; }
.st-key-jd_result h3 { margin: 4px 0 8px; font-size: 26px; line-height: 1.3; }
.st-key-jd_result p { color: var(--ink); margin: 10px 0 14px; max-width: 70ch; }
.hoot-badges { display: flex; gap: 8px; flex-wrap: wrap; }
.hoot-badge { background: var(--accent); color: #fff; font-size: 12px; font-weight: 700; padding: 4px 12px; border-radius: 999px;
  text-transform: capitalize; }
.hoot-badge.alt { background: var(--surface); color: var(--brand-deep); border: 1px solid var(--border); text-transform: none; }
.hoot-stat { background: var(--surface); border-radius: 16px; padding: 12px 16px; margin-bottom: 14px; }
.hoot-stat b { display: block; font-size: 26px; font-weight: 800; color: var(--ink); line-height: 1.1; }
.hoot-stat span { font-size: 13px; color: var(--muted); }
[class*="st-key-jd_skill_"], .st-key-jd_ask, .st-key-jd_flags { background: var(--surface); border: 1px solid var(--border);
  border-radius: 18px; padding: 14px 18px; margin-bottom: 14px; height: 100%; }
.hoot-card-title { font-weight: 700; font-size: 16px; color: var(--ink); margin-bottom: 8px; }
.hoot-chips, .hoot-legend { display: flex; flex-wrap: wrap; gap: 6px; }
.hoot-legend { margin-bottom: 12px; }
.hoot-chip { font-size: 13px; font-weight: 600; padding: 4px 11px; border-radius: 999px; line-height: 1.3; }
.hoot-chip.must { background: var(--accent-soft); color: var(--brand-deep); }
.hoot-chip.nice { background: transparent; color: var(--muted); border: 1px dashed var(--border); }
.hoot-group { font-weight: 700; font-size: 15px; color: var(--ink); margin: 14px 0 6px; }
.hoot-group small { color: var(--muted); font-weight: 600; margin-left: 4px; }
[class*="st-key-jd_q_"] { background: var(--surface); border: 1px solid var(--border); border-radius: 18px; padding: 14px 18px 8px;
  margin-bottom: 10px; }
[class*="st-key-jd_q_"] h3 { margin: 4px 0 6px; font-size: 17px; line-height: 1.4; font-weight: 700; }
[class*="st-key-jd_day_"] { background: var(--surface); border: 1px solid var(--border); border-radius: 18px; padding: 12px 18px 6px;
  margin-bottom: 10px; }
.hoot-day { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
.hoot-day-no { flex: none; background: var(--brand); color: #fff; font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 999px; }
.hoot-day b { font-size: 15px; color: var(--ink); }
.st-key-jd_ask ul, .st-key-jd_flags ul { margin: 0; padding-left: 18px; color: var(--ink); }
.st-key-jd_ask li, .st-key-jd_flags li { margin-bottom: 6px; }
.hoot-muted { color: var(--muted); list-style: none; margin-left: -18px; }

/* ---------- ai resume builder ---------- */
.st-key-rb_tab_control { margin-bottom: 6px; }
.st-key-rb_new, .st-key-rb_result { background: var(--surface); border: 1px solid var(--border); border-radius: 22px; padding: 22px 26px 18px; margin-bottom: 10px; }
.st-key-rb_result { background: var(--section); border: none; }
.st-key-rb_result h3 { margin: 4px 0 8px; font-size: 26px; line-height: 1.3; }
.st-key-rb_result p { color: var(--ink); margin: 6px 0 14px; max-width: 80ch; }
.st-key-rb_new [data-testid="stCaptionContainer"] { margin-top: -6px; }
.st-key-rb_empty { background: var(--surface); border: 2px dashed var(--border); border-radius: 22px; padding: 44px 24px 36px; }
.hoot-empty { text-align: center; }
.hoot-empty-icon { width: 72px; height: 72px; border-radius: 20px; background: var(--accent-soft); display: inline-flex; align-items: center;
  justify-content: center; font-size: 34px; margin-bottom: 14px; }
.hoot-empty h3 { margin: 0 0 6px; font-size: 22px; font-weight: 800; color: var(--ink); }
.hoot-empty p { margin: 0 0 18px; color: var(--muted); font-size: 15px; }
[class*="st-key-rb_card_"] { background: var(--surface); border: 1px solid var(--border); border-radius: 20px; padding: 16px 18px 12px;
  margin-bottom: 14px; transition: transform .15s, box-shadow .15s; }
[class*="st-key-rb_card_"]:hover { transform: translateY(-2px); box-shadow: 0 12px 28px color-mix(in srgb, var(--brand-deep) 12%, transparent); }
[class*="st-key-rb_card_"] .hoot-card-title { font-size: 17px; margin: 4px 0 2px; }
.hoot-card-sub { color: var(--muted); font-size: 13px; margin: 0 0 10px; min-height: 20px; }
.hoot-score { display: inline-block; background: var(--accent-soft); color: var(--brand-deep); font-weight: 700; font-size: 12px;
  padding: 3px 10px; border-radius: 999px; }
.hoot-chip.added { background: #DDF3E4; color: #1E6B3A; }
.hoot-chip.missing { background: transparent; color: var(--muted); border: 1px dashed var(--border); text-decoration: line-through; }
.hoot-verify { display: inline-block; background: #FBE7C6; color: #7A4B00; font-size: 11px; font-weight: 700; padding: 2px 8px;
  border-radius: 999px; margin-left: 6px; vertical-align: middle; }
.st-key-rb_preview { background: #fff; border: 1px solid var(--border); border-radius: 14px; padding: 36px 44px; max-width: 860px;
  box-shadow: 0 10px 30px color-mix(in srgb, var(--brand-deep) 8%, transparent); margin: 6px 0 20px; }
.hoot-cv { color: #1F2330; font-size: 14.5px; line-height: 1.5; }
.hoot-cv h1 { font-size: 28px; font-weight: 800; margin: 0 0 2px; letter-spacing: -0.3px; }
.hoot-cv .headline { font-size: 15px; font-weight: 700; color: var(--brand-deep); }
.hoot-cv .contact { font-size: 12.5px; color: #5B6170; margin: 4px 0 10px; }
.hoot-cv h2 { font-size: 13px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; color: var(--brand); margin: 18px 0 6px;
  padding-bottom: 4px; border-bottom: 1px solid var(--border); }
.hoot-cv .entry { margin-bottom: 10px; }
.hoot-cv .entry b { font-size: 15px; }
.hoot-cv .meta { font-size: 12.5px; color: #5B6170; font-style: italic; }
.hoot-cv p { margin: 4px 0; }
.hoot-cv ul { margin: 4px 0 0; padding-left: 20px; }
.hoot-cv li { margin-bottom: 3px; }
[class*="st-key-rb_change_"], .st-key-rb_gaps, .st-key-rb_notes { background: var(--surface); border: 1px solid var(--border);
  border-radius: 18px; padding: 14px 18px 8px; margin-bottom: 12px; height: 100%; }
.hoot-diff { border-left: 3px solid var(--accent-soft); padding: 4px 0 4px 12px; margin: 0 0 12px; }
.hoot-diff .new { color: var(--ink); font-size: 14.5px; }
.hoot-diff .old { color: var(--muted); font-size: 12.5px; margin-top: 3px; }
.hoot-reason { display: inline-block; margin-top: 4px; font-size: 12px; font-weight: 600; color: var(--brand-deep); background: var(--accent-soft);
  padding: 2px 8px; border-radius: 999px; }
.hoot-reason.kept { background: transparent; color: var(--muted); border: 1px dashed var(--border); }
.st-key-rb_gaps ul, .st-key-rb_notes ul { margin: 0; padding-left: 18px; color: var(--ink); }
.st-key-rb_gaps li, .st-key-rb_notes li { margin-bottom: 8px; }
.st-key-rb_notes small { color: var(--muted); font-weight: 600; margin-left: 4px; }

/* ---------- generic cards ---------- */
.st-key-question_card { background: var(--section); border-radius: 22px; padding: 22px 26px; }
.st-key-question_card h3 { margin: 4px 0 0; font-size: 22px; line-height: 1.35; }
.hoot-kicker { font-size: 12px; font-weight: 700; letter-spacing: .08em; color: var(--brand); text-transform: uppercase; }
.st-key-recent { background: var(--surface); border: 1px solid var(--border); border-radius: 22px; padding: 18px 22px; }
.st-key-playground { background: var(--surface); border: 1px solid var(--border); border-radius: 22px; padding: 6px 12px; }
.hoot-h2 { font-size: 24px; font-weight: 800; margin: 8px 0 4px; color: var(--ink); }
.hoot-sub { color: var(--muted); margin: 0 0 14px; }
[data-testid="stForm"] { border-radius: 22px; border-color: var(--border); background: var(--surface); padding: 22px 24px; }
.stButton button[kind="primary"] { font-weight: 700; box-shadow: 0 8px 18px color-mix(in srgb, var(--accent) 35%, transparent); }
[data-testid="stMetric"] { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 10px 14px; }
</style>
"""

CSS = _fill(_CSS, P)
