# Rico AI UI Polish Plan

This note documents the non-breaking cosmetic and UX improvement scope for the Rico AI public landing page and Next.js frontend.

## Scope

- Keep API routes, backend logic, webhooks, automation scripts, and repository structure unchanged.
- Improve perceived polish, mobile responsiveness, accessibility, and theme consistency.
- Preserve existing public CTAs, Jotform links, Telegram positioning, and dashboard/app references.

## Landing page priorities

1. Strengthen dark cyber-luxury visual consistency with the existing purple and teal palette.
2. Improve responsive behavior for navigation, hero CTAs, mockups, cards, grids, and footer.
3. Add accessibility polish: focus-visible states, reduced-motion support, visible cursor fallback on touch devices, and safer contrast tokens.
4. Reduce layout instability with better image/media defaults and mobile-safe spacing.
5. Add progressive enhancement only; the page must remain usable without JavaScript.

## Next.js frontend priorities

1. Keep global tokens aligned with the landing page.
2. Improve base focus states, selection styling, scrollbars, and body background treatment.
3. Add reduced-motion handling for users who request less animation.
4. Avoid changes to data fetching, auth, chat logic, API clients, or route behavior.

## Validation checklist

- Landing page loads from `index.html` redirect/fallback.
- All existing CTA links remain intact.
- Mobile widths under 480px avoid horizontal overflow.
- Reduced-motion users do not receive heavy animations.
- Keyboard users can see focus states.
- No backend, webhook, or automation files are changed.
