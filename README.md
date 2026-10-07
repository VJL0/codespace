# CodeSpace

CodeSpace is a real-time classroom coding platform designed to help teachers monitor, support, and interact with students while they code.

Students can join a classroom and work in browser-based coding environments, while teachers can view student activity, manage sessions, and provide help without constantly moving between computers.

> **Status:** CodeSpace is currently under active development.

## Why I Built It

I came up with CodeSpace while thinking about how I would teach programming if I became a lead instructor for Temple University's STEM Scholars summer program, which works with middle school students.

As a computer science student and software developer, I wanted a better way to manage a classroom where every student is coding at the same time. It can be difficult for an instructor to see who is stuck, understand what students are working on, and provide help without constantly walking between computers.

After researching the problem further, I found other programming instructors and teachers online describing similar challenges. That made me realize this was not just a problem I might face in my own classroom, so I decided to keep building CodeSpace into something that could be useful beyond my own teaching experience.

The goal is to give instructors a central place to monitor student coding sessions, manage the classroom, and help students in real time while keeping the experience simple for students.

CodeSpace started as a tool I wanted for my own classroom and has grown into an attempt to solve a broader problem in teaching programming.

## Features

* Real-time classroom coding experience
* Browser-based coding environment for students
* Teacher dashboard for monitoring student activity
* Classroom creation and management
* Student access through classroom codes
* Role-based permissions for teachers and students
* Backend code execution
* Authentication and session management
* Real-time communication between clients and the server

More classroom-management and collaboration features are currently in development.

## Tech Stack

### Frontend

* React
* TypeScript
* Vite
* Tailwind CSS
* Apollo Client

### Backend

* Python
* FastAPI
* GraphQL
* SQLAlchemy
* PostgreSQL
* WebSockets

### Infrastructure

* Docker
* Docker Compose
* Alembic

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the code map and [docs/auth.md](docs/auth.md) for authentication.

CodeSpace uses a full-stack architecture with a React frontend and Python backend.

The backend is structured so API logic, business logic, and data access remain separated as the application grows.

```text
Frontend
   |
   | GraphQL / WebSockets
   v
FastAPI Backend
   |
   |-- Resolvers
   |-- Services
   |-- Repositories
   |-- Models
   |
   v
PostgreSQL
```

## Project Structure

```text
codespace/
├── frontend/          # React + TypeScript frontend
├── backend/           # FastAPI backend
├── docker-compose.yml
└── README.md
```

## Running Locally

### Requirements

* Node.js
* [pnpm](https://pnpm.io/installation)
* Python 3.14+
* [uv](https://docs.astral.sh/uv/getting-started/installation/)
* Docker + Docker Compose (for PostgreSQL)

Clone the repository:

```bash
git clone https://github.com/VJL0/codespace.git
cd codespace
```

### 1. Start the database

```bash
cd backend
cp .env.example .env   # first time only
docker compose up -d
```

### 2. Run the backend

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

uvicorn listens on `http://localhost:8000`, but use the app through Vite below.

### 3. Run the frontend

```bash
cd frontend
pnpm install
pnpm dev
```

The app will be available at `http://localhost:5173`. Vite proxies `/api` to
the backend, so the SPA and API share one origin, as they do in production.

### Same-origin deployment

The SPA and API are always served from one origin: the SPA at `/` and FastAPI
at `/api/*`, routed by the edge or reverse proxy. The API sends no CORS
headers, and its CSRF check refuses state-changing requests that don't come
from that origin. `APP_URL` in `backend/.env` is that origin.

Each provider's OAuth app must list `{APP_URL}/api/auth/{provider}/callback`
as a redirect URI (locally `http://localhost:5173/api/auth/google/callback`,
and the same for `microsoft` and `github`).

Behind a proxy, run uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy
IPs>` so the app sees the client's address rather than the proxy's.

Vercel Cron runs the daily cleanup in `vercel.json` (`/api/cron/purge-expired`).
Set `CRON_SECRET` in the Vercel project to the backend's value. Vercel calls
the production deployment's `*.vercel.app` URL, not your domain, so add that
host to `ALLOWED_HOSTS` too.

Microsoft has no `email_verified` claim; its `xms_edov` optional claim says
whether an email is verified. In the Entra app registration, under **Token
configuration**, add the `email` and `xms_edov` optional claims to the ID
token. Without them, Microsoft emails count as unverified.

## What I'm Working On

Current development is focused on:

* Improving the live classroom experience
* Expanding teacher classroom controls
* Improving real-time student monitoring
* Building a better browser-based coding environment
* Improving code execution and session management
* Making it easier for students to join and start coding

## What I Want to Explore

CodeSpace combines several areas of software engineering that I am particularly interested in:

* Developer tools
* Education technology
* Real-time applications
* Backend architecture
* Collaborative coding environments
* Making programming more accessible

I want to continue exploring how better developer tooling can make programming easier to teach, learn, and collaborate on.

## Author

Built by [Victor Jimenez-Lorenzo](https://github.com/VJL0).
