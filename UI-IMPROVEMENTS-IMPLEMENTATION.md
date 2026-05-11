# Rico AI - UI Polish & Accessibility Implementation Guide

**Repository**: `Binz2008-star/job-automation-system-1`  
**Branch Recommendation**: `feat/ui-polish-v2`  
**Goal**: Cosmetic enhancements + Full WCAG 2.2 AA Accessibility without breaking any existing structure, links, APIs, buttons, or animations.

> Note: This guide is documentation. Apply code changes section by section and test before merging. The middleware section is optional and should only be applied if protected-route behavior is desired and verified.

## 1. Design Tokens & Theme Unity

Add or align these CSS variables in both:

- `rico-ai-landing.html` inside the main `<style>` block
- `apps/web/app/globals.css`

```css
:root {
  --bg: #070712;
  --s1: #0e0e20;
  --s2: #14142a;
  --accent: #5b4fff;
  --accent-glow: rgba(91, 79, 255, 0.4);
  --teal: #00c9a7;
  --teal-glow: rgba(0, 201, 167, 0.3);
  --border: rgba(255,255,255,0.08);
  --text: #eeeef5;
  --text-muted: #a0a0b8;
}
```

For the Next.js app, keep Tailwind directives at the top of `apps/web/app/globals.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  /* shared tokens above */
}

html,
body {
  scroll-behavior: smooth;
}
```

## 2. Global Accessibility Styles

Add shared focus, skip-link, reduced-motion, and touch-target utilities.

```css
body::after {
  content: '';
  position: fixed;
  inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.03'/%3E%3C/svg%3E");
  pointer-events: none;
  z-index: 1;
  mix-blend-mode: overlay;
  opacity: 0.4;
}

button:focus-visible,
a:focus-visible,
input:focus-visible,
textarea:focus-visible,
select:focus-visible,
[tabindex]:focus-visible {
  outline: 3px solid var(--teal);
  outline-offset: 4px;
  border-radius: 8px;
}

.skip-link {
  position: absolute;
  top: -48px;
  left: 6px;
  background: var(--accent);
  color: white;
  padding: 8px 16px;
  z-index: 10000;
  text-decoration: none;
  border-radius: 0 0 6px 6px;
  transition: top 0.3s;
}

.skip-link:focus {
  top: 0;
}

a,
button,
[role='button'] {
  min-height: 44px;
  min-width: 44px;
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }

  .custom-cursor,
  .cur,
  .cur-r {
    display: none !important;
  }
}

@media (hover: none), (pointer: coarse) {
  .custom-cursor,
  .cur,
  .cur-r {
    display: none !important;
  }
}
```

## 3. Landing Page Structural Improvements

Add a skip link immediately after `<body>`:

```html
<a href="#main-content" class="skip-link">Skip to main content</a>
```

Wrap the main content in a semantic landmark:

```html
<main id="main-content" role="main">
  <!-- Existing page sections go here -->
</main>
```

Use an accessible navigation label:

```html
<nav aria-label="Main navigation">
  <!-- Existing nav content -->
</nav>
```

Use descriptive CTA labels:

```html
<a
  href="https://form.jotform.com/261278237812056"
  target="_blank"
  rel="noopener noreferrer"
  class="btn-primary"
  aria-label="Start using Rico AI with the early access form"
>
  Start for free
</a>
```

For visual mockups, add an accessible role and label:

```html
<div class="hero-mockup" role="img" aria-label="Preview of the Rico AI dashboard showing UAE job matches and Telegram alerts">
  <!-- Existing mockup -->
</div>
```

## 4. Custom Cursor Fallback

Use this script pattern to disable the custom cursor for reduced-motion and touch users.

```js
const shouldDisableCustomCursor =
  window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
  window.matchMedia('(hover: none)').matches ||
  'ontouchstart' in window;

if (shouldDisableCustomCursor) {
  document.documentElement.style.setProperty('--cursor-display', 'none');
  document.body.classList.add('no-custom-cursor');
}
```

Add supporting CSS:

```css
.no-custom-cursor,
.no-custom-cursor * {
  cursor: auto !important;
}
```

## 5. Button Polish

```css
.btn-primary {
  background: var(--accent);
  color: white;
  padding: 14px 28px;
  border-radius: 12px;
  font-weight: 600;
  box-shadow: 0 4px 20px var(--accent-glow);
  transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 25px var(--accent-glow);
}

.btn-primary:active {
  transform: translateY(0);
}
```

## 6. Other Required Accessibility Changes

- Add `alt=""` to decorative images.
- Add meaningful `alt` text to informative images.
- Use exactly one `<h1>` per page.
- Follow heading hierarchy: `<h1>`, then `<h2>`, then `<h3>`.
- Add `role="region"` and `aria-labelledby` to major sections where useful.
- Ensure mobile buttons and links meet the 44px minimum touch target recommendation.
- Ensure all external links that open in a new tab include `rel="noopener noreferrer"`.
- Ensure keyboard focus order follows visual order.
- Avoid keyboard traps in modals, drawers, and custom overlays.
- Keep visible text descriptive; avoid vague link-only text such as `click here`.

## 7. Optional Middleware for Protected Routes

Create `apps/web/middleware.ts` only if protected routes should redirect unauthenticated users to login.

```ts
import { NextRequest, NextResponse } from 'next/server';

export function middleware(request: NextRequest) {
  const token = request.cookies.get('rico_auth_token')?.value;

  const protectedPaths = ['/dashboard', '/chat', '/jobs', '/applications', '/profile'];
  const isProtected = protectedPaths.some((path) =>
    request.nextUrl.pathname.startsWith(path)
  );

  if (isProtected && !token) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
};
```

Important: This is not purely cosmetic. Test authentication flow before applying.

## 8. Quick Validation Checklist

- Lighthouse Accessibility score is 95 or higher.
- Tab navigation works logically.
- Every interactive element has a visible focus indicator.
- Reduced motion is respected.
- All buttons and links meet minimum mobile touch-target sizing.
- Skip link works and lands on the main content.
- No keyboard traps are present.
- Custom cursor is disabled on mobile, touch, and reduced-motion contexts.
- Existing Jotform links still work.
- Existing Telegram/API references remain unchanged.
- No backend, webhook, or automation behavior changes unless intentionally modified.

## 9. Recommended Commit Flow

```bash
git checkout -b feat/ui-polish-v2
# apply changes section by section
npm run lint
npm run build
git add rico-ai-landing.html apps/web/app/globals.css UI-IMPROVEMENTS-IMPLEMENTATION.md
git commit -m "feat(ui): improve accessibility and polish"
git push origin feat/ui-polish-v2
```

Then open a pull request from `feat/ui-polish-v2` to `main`.
