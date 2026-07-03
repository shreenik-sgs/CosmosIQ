"""Deterministic local celestial SVG assets for the Universe Canvas.

These are small repo-native images, not fetched assets. The renderer maps each
semantic object type to exactly one image so the visual hierarchy cannot drift:

Mega Theme -> infinity galaxy, Theme -> Milky Way, Value Chain -> solar system,
Bottleneck -> star, Stock -> planet, Supplier/Customer -> moon.
"""

from __future__ import annotations

from typing import Dict


CELESTIAL_ASSETS: Dict[str, str] = {
    "mega-theme-galaxy.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 180">
  <defs>
    <radialGradient id="core" cx="50%" cy="50%" r="58%">
      <stop offset="0" stop-color="#fff3cc"/>
      <stop offset=".16" stop-color="#d4bd8b" stop-opacity=".92"/>
      <stop offset=".44" stop-color="#8c78a7" stop-opacity=".42"/>
      <stop offset="1" stop-color="#171a52" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="haze" cx="50%" cy="52%" r="58%">
      <stop offset="0" stop-color="#b99684" stop-opacity=".52"/>
      <stop offset=".34" stop-color="#755b9f" stop-opacity=".28"/>
      <stop offset="1" stop-color="#171a52" stop-opacity="0"/>
    </radialGradient>
    <filter id="mist" x="-25%" y="-70%" width="150%" height="240%">
      <feGaussianBlur stdDeviation="9" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="softline" x="-25%" y="-70%" width="150%" height="240%">
      <feGaussianBlur stdDeviation="1.2" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <ellipse cx="260" cy="92" rx="150" ry="50" fill="url(#haze)" filter="url(#mist)" opacity=".9"/>
  <g fill="none" stroke-linecap="round" stroke-linejoin="round" filter="url(#softline)">
    <path d="M18 78 C92 18 183 34 260 90 C337 146 428 162 502 102"
      stroke="#8176a8" stroke-width="7" opacity=".34"/>
    <path d="M18 78 C92 138 183 122 260 90 C337 58 428 42 502 102"
      stroke="#5f6aa6" stroke-width="7" opacity=".28"/>
    <path d="M26 78 C100 30 183 42 260 90 C337 138 420 150 494 102"
      stroke="#d3c2ac" stroke-width="3.4" opacity=".46"/>
    <path d="M26 78 C100 126 183 114 260 90 C337 66 420 54 494 102"
      stroke="#8e83b8" stroke-width="3.2" opacity=".34"/>
    <path d="M58 82 C132 58 202 66 260 90 C318 114 388 122 462 98"
      stroke="#f1dac0" stroke-width="1.4" opacity=".38"/>
  </g>
  <ellipse cx="260" cy="90" rx="56" ry="33" fill="url(#core)" filter="url(#mist)"/>
  <g fill="#fff" opacity=".74">
    <circle cx="64" cy="72" r="2"/><circle cx="132" cy="92" r="1.2"/>
    <circle cx="195" cy="70" r="1.1"/><circle cx="335" cy="112" r="1.3"/>
    <circle cx="400" cy="92" r="1.6"/><circle cx="466" cy="107" r="1.1"/>
  </g>
</svg>""",
    "theme-milky-way.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 180">
  <defs>
    <radialGradient id="bulge" cx="50%" cy="50%" r="38%">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset=".22" stop-color="#ffe8a6"/>
      <stop offset=".55" stop-color="#8fb5ee" stop-opacity=".58"/>
      <stop offset="1" stop-color="#15203d" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="halo" cx="50%" cy="50%" r="65%">
      <stop offset="0" stop-color="#c6dcff" stop-opacity=".42"/>
      <stop offset=".62" stop-color="#4f6798" stop-opacity=".26"/>
      <stop offset="1" stop-color="#000" stop-opacity="0"/>
    </radialGradient>
    <filter id="soft" x="-40%" y="-50%" width="180%" height="200%">
      <feGaussianBlur stdDeviation="3" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="grain" x="-30%" y="-30%" width="160%" height="160%">
      <feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" seed="23"/>
      <feColorMatrix type="saturate" values="0"/>
      <feComponentTransfer><feFuncA type="table" tableValues="0 .16"/></feComponentTransfer>
    </filter>
  </defs>
  <ellipse cx="120" cy="90" rx="100" ry="72" fill="url(#halo)" filter="url(#soft)" opacity=".95"/>
  <g fill="none" stroke-linecap="round" filter="url(#soft)" transform="rotate(-22 120 90)">
    <path d="M118 89 C92 74 62 78 40 96 C70 43 138 38 163 70"
      stroke="#d7e7ff" stroke-width="11" opacity=".58"/>
    <path d="M122 92 C150 108 180 102 202 84 C174 137 104 142 78 110"
      stroke="#b7cff7" stroke-width="12" opacity=".52"/>
    <path d="M118 84 C138 62 178 54 207 68 C177 31 102 27 74 68"
      stroke="#6f86b8" stroke-width="10" opacity=".42"/>
    <path d="M122 96 C102 118 62 126 33 112 C63 149 138 153 166 112"
      stroke="#6b82b3" stroke-width="10" opacity=".36"/>
    <path d="M116 89 C96 85 78 91 62 103" stroke="#ffb5a3" stroke-width="2.4" opacity=".55"/>
    <path d="M124 91 C146 94 164 88 181 77" stroke="#ffb5a3" stroke-width="2.2" opacity=".45"/>
  </g>
  <ellipse cx="120" cy="90" rx="38" ry="22" fill="url(#bulge)" filter="url(#soft)" transform="rotate(-22 120 90)"/>
  <ellipse cx="120" cy="90" rx="103" ry="72" fill="#fff" filter="url(#grain)" opacity=".8"/>
  <g fill="#fff" opacity=".72">
    <circle cx="65" cy="62" r="1.4"/><circle cx="86" cy="105" r="1.1"/>
    <circle cx="103" cy="52" r="1.2"/><circle cx="145" cy="126" r="1.3"/>
    <circle cx="166" cy="70" r="1.1"/><circle cx="183" cy="102" r="1.4"/>
    <circle cx="55" cy="112" r="1"/><circle cx="198" cy="80" r=".9"/>
  </g>
</svg>""",
    "value-chain-solar-system.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 180">
  <defs>
    <radialGradient id="sun" cx="42%" cy="38%" r="58%">
      <stop offset="0" stop-color="#fff7ca"/>
      <stop offset=".18" stop-color="#ffd55c"/>
      <stop offset=".48" stop-color="#ff8b22"/>
      <stop offset=".82" stop-color="#ff5d13" stop-opacity=".54"/>
      <stop offset="1" stop-color="#ff4b00" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="planetBlue" cx="34%" cy="30%" r="70%">
      <stop offset="0" stop-color="#dcefff"/><stop offset=".45" stop-color="#5d8eb0"/>
      <stop offset="1" stop-color="#16253d"/>
    </radialGradient>
    <radialGradient id="planetWarm" cx="35%" cy="28%" r="70%">
      <stop offset="0" stop-color="#ffe0b2"/><stop offset=".48" stop-color="#a75c34"/>
      <stop offset="1" stop-color="#2b1514"/>
    </radialGradient>
    <radialGradient id="jupiter" cx="35%" cy="30%" r="72%">
      <stop offset="0" stop-color="#f7d7a4"/><stop offset=".42" stop-color="#9c664a"/>
      <stop offset="1" stop-color="#2b1715"/>
    </radialGradient>
    <filter id="sunGlow" x="-80%" y="-80%" width="260%" height="260%">
      <feGaussianBlur stdDeviation="7" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="dust" x="-20%" y="-40%" width="140%" height="180%">
      <feGaussianBlur stdDeviation="5"/>
    </filter>
  </defs>
  <rect width="320" height="180" fill="transparent"/>
  <path d="M0 70 C76 20 135 76 205 90 C254 100 286 62 320 48"
    fill="none" stroke="#b596ad" stroke-width="22" stroke-opacity=".18" filter="url(#dust)"/>
  <path d="M0 92 C86 52 150 105 220 112 C263 116 294 85 320 72"
    fill="none" stroke="#d0a36d" stroke-width="12" stroke-opacity=".16" filter="url(#dust)"/>
  <g fill="#fff" opacity=".72">
    <circle cx="18" cy="18" r=".9"/><circle cx="56" cy="34" r="1.1"/><circle cx="88" cy="18" r=".8"/>
    <circle cx="136" cy="28" r="1"/><circle cx="214" cy="22" r=".8"/><circle cx="285" cy="30" r="1.2"/>
    <circle cx="42" cy="116" r=".8"/><circle cx="110" cy="140" r="1"/><circle cx="240" cy="136" r=".9"/>
  </g>
  <circle cx="150" cy="86" r="43" fill="url(#sun)" filter="url(#sunGlow)"/>
  <circle cx="150" cy="86" r="34" fill="none" stroke="#fff2aa" stroke-width="3" stroke-opacity=".45"/>
  <circle cx="86" cy="38" r="12" fill="url(#planetBlue)" opacity=".88"/>
  <circle cx="72" cy="18" r="10" fill="#3b4159" opacity=".62"/>
  <circle cx="104" cy="108" r="8" fill="url(#planetWarm)"/>
  <circle cx="205" cy="112" r="10" fill="url(#planetWarm)"/>
  <circle cx="232" cy="75" r="16" fill="url(#planetBlue)"/>
  <circle cx="285" cy="40" r="24" fill="url(#jupiter)"/>
  <path d="M263 37 C278 30 298 32 310 45" fill="none" stroke="#f0c384" stroke-width="3" stroke-opacity=".38"/>
  <ellipse cx="48" cy="153" rx="58" ry="18" fill="none" stroke="#b89980" stroke-width="8" stroke-opacity=".34" transform="rotate(9 48 153)"/>
  <circle cx="48" cy="151" r="34" fill="url(#planetWarm)" opacity=".72"/>
</svg>""",
    "bottleneck-star.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 180">
  <defs>
    <radialGradient id="sunBase" cx="42%" cy="36%" r="66%">
      <stop offset="0" stop-color="#fff6a8"/>
      <stop offset=".2" stop-color="#ffb92d"/>
      <stop offset=".55" stop-color="#ff6f00"/>
      <stop offset=".84" stop-color="#d63200"/>
      <stop offset="1" stop-color="#8b1200"/>
    </radialGradient>
    <radialGradient id="corona" cx="50%" cy="50%" r="58%">
      <stop offset=".58" stop-color="#ff6b00" stop-opacity=".18"/>
      <stop offset=".82" stop-color="#ff2b00" stop-opacity=".54"/>
      <stop offset="1" stop-color="#ff1900" stop-opacity="0"/>
    </radialGradient>
    <filter id="sunGlow" x="-70%" y="-70%" width="240%" height="240%">
      <feGaussianBlur stdDeviation="6" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="solarTexture" x="-20%" y="-20%" width="140%" height="140%">
      <feTurbulence type="fractalNoise" baseFrequency=".055" numOctaves="5" seed="41"/>
      <feColorMatrix type="matrix" values="1.2 0 0 0 0.2  0 .55 0 0 .04  0 0 .08 0 0  0 0 0 .42 0"/>
      <feBlend mode="screen" in2="SourceGraphic"/>
    </filter>
  </defs>
  <circle cx="90" cy="90" r="80" fill="url(#corona)" filter="url(#sunGlow)"/>
  <circle cx="90" cy="90" r="62" fill="url(#sunBase)" filter="url(#sunGlow)"/>
  <circle cx="90" cy="90" r="61" fill="#ff7a00" filter="url(#solarTexture)" opacity=".92"/>
  <g fill="none" stroke-linecap="round" opacity=".78">
    <path d="M31 112 C18 108 10 96 6 84" stroke="#ff4a00" stroke-width="4" filter="url(#sunGlow)"/>
    <path d="M145 52 C160 48 169 57 174 66" stroke="#ff9a1f" stroke-width="3.2" filter="url(#sunGlow)"/>
    <path d="M132 38 C145 30 156 32 164 40" stroke="#ff2f00" stroke-width="2.4" filter="url(#sunGlow)"/>
  </g>
  <g fill="#fff5b8" opacity=".75" filter="url(#sunGlow)">
    <ellipse cx="54" cy="122" rx="18" ry="8" transform="rotate(-22 54 122)"/>
    <ellipse cx="128" cy="54" rx="13" ry="5" transform="rotate(30 128 54)"/>
  </g>
</svg>""",
    "stock-planet.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 170 170">
  <defs>
    <radialGradient id="planet" cx="66%" cy="36%" r="72%">
      <stop offset="0" stop-color="#eef8ff"/>
      <stop offset=".18" stop-color="#6fb5ff"/>
      <stop offset=".48" stop-color="#245fa8"/>
      <stop offset=".72" stop-color="#10284e"/>
      <stop offset="1" stop-color="#02050c"/>
    </radialGradient>
    <radialGradient id="rim" cx="72%" cy="40%" r="58%">
      <stop offset=".62" stop-color="#1a5ab4" stop-opacity="0"/>
      <stop offset=".86" stop-color="#38a9ff" stop-opacity=".62"/>
      <stop offset="1" stop-color="#9fdcff" stop-opacity="0"/>
    </radialGradient>
    <filter id="soft" x="-35%" y="-35%" width="170%" height="170%">
      <feGaussianBlur stdDeviation="2.2" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="clouds" x="-20%" y="-20%" width="140%" height="140%">
      <feTurbulence type="fractalNoise" baseFrequency=".035" numOctaves="5" seed="73"/>
      <feColorMatrix type="matrix" values=".35 .35 .35 0 .05  .35 .45 .55 0 .08  .45 .55 .75 0 .18  0 0 0 .5 0"/>
      <feBlend mode="screen" in2="SourceGraphic"/>
    </filter>
    <clipPath id="disc"><circle cx="86" cy="84" r="58"/></clipPath>
  </defs>
  <circle cx="86" cy="84" r="62" fill="#03060d" opacity=".9"/>
  <g clip-path="url(#disc)">
    <circle cx="86" cy="84" r="58" fill="url(#planet)" filter="url(#soft)"/>
    <circle cx="86" cy="84" r="58" fill="#5eb6ff" filter="url(#clouds)" opacity=".72"/>
    <path d="M33 112 C58 92 76 107 102 88 C116 78 132 82 144 70"
      fill="none" stroke="#d8edff" stroke-opacity=".42" stroke-width="8"/>
    <path d="M50 60 C70 74 86 58 111 63 C124 66 133 56 145 48"
      fill="none" stroke="#eaf6ff" stroke-opacity=".34" stroke-width="5"/>
    <rect x="15" y="20" width="62" height="130" fill="#000" opacity=".45"/>
    <circle cx="86" cy="84" r="58" fill="url(#rim)"/>
  </g>
  <circle cx="86" cy="84" r="58" fill="none" stroke="#78beff" stroke-opacity=".36" stroke-width="2"/>
</svg>""",
    "supplier-customer-moon.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 150 150">
  <defs>
    <radialGradient id="moon" cx="38%" cy="30%" r="68%">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset=".28" stop-color="#f1eee7"/>
      <stop offset=".66" stop-color="#c9c6bd"/>
      <stop offset="1" stop-color="#8f8b82"/>
    </radialGradient>
    <filter id="moonTexture" x="-20%" y="-20%" width="140%" height="140%">
      <feTurbulence type="fractalNoise" baseFrequency=".075" numOctaves="4" seed="91"/>
      <feColorMatrix type="matrix" values=".45 .45 .45 0 .12  .45 .45 .45 0 .12  .45 .45 .45 0 .12  0 0 0 .24 0"/>
      <feBlend mode="multiply" in2="SourceGraphic"/>
    </filter>
    <clipPath id="moonDisc"><circle cx="75" cy="75" r="58"/></clipPath>
  </defs>
  <circle cx="75" cy="75" r="59" fill="url(#moon)"/>
  <g clip-path="url(#moonDisc)">
    <circle cx="75" cy="75" r="58" fill="url(#moon)" filter="url(#moonTexture)"/>
    <g fill="#8e8a81" opacity=".28">
      <circle cx="54" cy="64" r="12"/><circle cx="88" cy="61" r="10"/>
      <circle cx="100" cy="38" r="8"/><circle cx="45" cy="98" r="7"/>
      <circle cx="82" cy="102" r="15"/><circle cx="111" cy="82" r="6"/>
      <circle cx="61" cy="34" r="5"/><circle cx="33" cy="75" r="5"/>
    </g>
    <path d="M31 107 C54 126 101 126 122 91" fill="none" stroke="#fff" stroke-opacity=".18" stroke-width="8"/>
    <rect x="113" y="12" width="22" height="124" fill="#000" opacity=".08"/>
  </g>
  <circle cx="75" cy="75" r="58" fill="none" stroke="#f4f1e8" stroke-opacity=".32" stroke-width="2"/>
</svg>""",
}
