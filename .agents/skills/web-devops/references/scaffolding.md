# Project Scaffolding Reference

## T3 Stack (Next.js + tRPC + Prisma/Drizzle + NextAuth + Tailwind + Zod)

Bootstrap with:
```bash
pnpm create t3-app@latest my-app
# Select: Next.js App Router, TypeScript, tRPC, Prisma, NextAuth, Tailwind, Zod
```

```
my-t3-app/
├── .github/
│   └── workflows/
│       └── ci.yml
├── prisma/
│   ├── schema.prisma        # DB schema — source of truth
│   └── migrations/
├── public/
├── src/
│   ├── app/                 # Next.js App Router pages
│   │   ├── _components/     # Page-scoped components (not shared)
│   │   ├── api/
│   │   │   ├── auth/[...nextauth]/route.ts
│   │   │   └── trpc/[trpc]/route.ts
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components/
│   │   └── ui/              # shadcn/ui components
│   ├── env.js               # @t3-oss/env-nextjs — validated env vars
│   ├── server/
│   │   ├── api/
│   │   │   ├── routers/     # One file per domain (post.ts, user.ts, etc.)
│   │   │   ├── root.ts      # Compose all routers here
│   │   │   └── trpc.ts      # createTRPCRouter, publicProcedure, protectedProcedure
│   │   ├── auth.ts          # NextAuth config
│   │   └── db.ts            # Prisma client singleton
│   ├── styles/
│   │   └── globals.css
│   └── trpc/
│       ├── react.tsx         # TRPCReactProvider + hooks
│       └── server.ts         # Server-side caller (RSC use)
├── .env.example
├── .gitignore
├── next.config.js
├── package.json
├── prettier.config.js
├── tailwind.config.ts
└── tsconfig.json
```

### T3 `.env.example`
```bash
# Database — use a managed Postgres (Neon, Supabase, Railway, PlanetScale)
DATABASE_URL="postgresql://user:pass@host:5432/db?sslmode=require"

# NextAuth
NEXTAUTH_SECRET="generate-with: openssl rand -base64 32"
NEXTAUTH_URL="http://localhost:3000"

# OAuth providers (add what you need)
DISCORD_CLIENT_ID=""
DISCORD_CLIENT_SECRET=""
GITHUB_CLIENT_ID=""
GITHUB_CLIENT_SECRET=""
GOOGLE_CLIENT_ID=""
GOOGLE_CLIENT_SECRET=""
```

### T3 `env.js` (type-safe env validation)
```typescript
import { createEnv } from "@t3-oss/env-nextjs";
import { z } from "zod";

export const env = createEnv({
  server: {
    DATABASE_URL: z.string().url(),
    NEXTAUTH_SECRET: z.string().min(1),
    NEXTAUTH_URL: z.preprocess(
      (str) => process.env.VERCEL_URL ?? str,
      z.string().url()
    ),
  },
  client: {
    // NEXT_PUBLIC_ vars go here
  },
  runtimeEnv: {
    DATABASE_URL: process.env.DATABASE_URL,
    NEXTAUTH_SECRET: process.env.NEXTAUTH_SECRET,
    NEXTAUTH_URL: process.env.NEXTAUTH_URL,
  },
});
```

### T3 tRPC Router Pattern
```typescript
// src/server/api/routers/post.ts
import { z } from "zod";
import { createTRPCRouter, protectedProcedure, publicProcedure } from "~/server/api/trpc";

export const postRouter = createTRPCRouter({
  getAll: publicProcedure.query(async ({ ctx }) => {
    return ctx.db.post.findMany({ orderBy: { createdAt: "desc" } });
  }),

  create: protectedProcedure
    .input(z.object({ title: z.string().min(1).max(100), content: z.string() }))
    .mutation(async ({ ctx, input }) => {
      return ctx.db.post.create({
        data: { ...input, authorId: ctx.session.user.id },
      });
    }),
});
```

---



```
my-app/
├── .github/
│   └── workflows/
│       └── ci.yml
├── app/
│   ├── (auth)/
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   ├── api/
│   │   └── health/route.ts
│   ├── layout.tsx
│   └── page.tsx
├── components/
│   ├── ui/          # shadcn/ui or custom primitives
│   └── shared/
├── lib/
│   ├── db.ts        # Prisma client singleton
│   └── utils.ts
├── prisma/
│   └── schema.prisma
├── public/
├── tests/
│   ├── unit/
│   └── e2e/         # Playwright
├── .env.example
├── .eslintrc.json
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── next.config.ts
├── package.json
├── prettier.config.js
└── tsconfig.json
```

## Express / Node.js API (TypeScript)

```
my-api/
├── .github/workflows/
├── src/
│   ├── config/      # env, db config
│   ├── controllers/
│   ├── middleware/  # auth, error handler, logger
│   ├── models/      # DB models / schemas
│   ├── routes/
│   ├── services/    # business logic
│   ├── utils/
│   └── index.ts     # app entry point
├── tests/
│   ├── unit/
│   └── integration/
├── .env.example
├── Dockerfile
├── package.json
└── tsconfig.json
```

## FastAPI (Python)

```
my-api/
├── .github/workflows/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       └── router.py
│   ├── core/
│   │   ├── config.py    # pydantic-settings
│   │   └── security.py
│   ├── db/
│   │   ├── base.py      # SQLAlchemy base
│   │   └── session.py
│   ├── models/          # SQLAlchemy models
│   ├── schemas/         # Pydantic schemas
│   ├── services/
│   └── main.py
├── tests/
├── .env.example
├── Dockerfile
├── pyproject.toml       # or requirements.txt
└── alembic.ini
```

## MERN Stack

```
mern-app/
├── client/              # React frontend (Vite)
│   ├── src/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── pages/
│   │   ├── store/       # Redux or Zustand
│   │   └── main.tsx
│   └── package.json
├── server/              # Express backend
│   ├── src/
│   │   ├── controllers/
│   │   ├── middleware/
│   │   ├── models/      # Mongoose schemas
│   │   ├── routes/
│   │   └── index.ts
│   └── package.json
├── docker-compose.yml
└── .github/workflows/
```

---

## Essential Config Files

### .gitignore (Node.js)
```
node_modules/
.env
.env.local
.next/
dist/
coverage/
*.log
```

### .env.example
```
# App
NODE_ENV=development
PORT=3000

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/mydb

# Auth
JWT_SECRET=your-secret-here
JWT_EXPIRES_IN=7d

# External APIs
STRIPE_SECRET_KEY=
SENDGRID_API_KEY=
```

### tsconfig.json (strict)
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "outDir": "dist",
    "rootDir": "src",
    "esModuleInterop": true,
    "skipLibCheck": true
  }
}
```