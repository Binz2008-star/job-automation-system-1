# Rico Web App

Next.js frontend for Rico AI.

## Features

- Chat-style Rico interface
- Mobile-friendly layout
- Streaming-style interaction feel
- Persistent conversation UX
- FastAPI backend integration

## Local development

```bash
cd apps/web
npm install
npm run dev
```

## Environment

```bash
NEXT_PUBLIC_RICO_API=http://localhost:8000
```

## Expected backend route

```http
POST /chat
```

Example request:

```json
{
  "user_id": "web-user",
  "message": "Find UAE operations roles"
}
```

Example response:

```json
{
  "reply": "Rico response"
}
```

## Planned upgrades

- WebSocket streaming
- Rich job cards
- Semantic memory timeline
- Notification center
- Interview prep cards
- Mobile push notifications
- Voice interaction
