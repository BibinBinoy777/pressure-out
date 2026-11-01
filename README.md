# Pressure Out

### Your Work. Your Chaos. Your People.

**Work is serious. Talking about it doesn't have to be.**

Pressure Out is a privacy-first workplace social platform where people can share workplace experiences, discuss professional challenges, express frustrations, exchange office humour, share resignation stories, and create AI-assisted memes without being required to reveal their real-world identity.

The platform creates a space for honest workplace conversations through pseudonymous identities, anonymous participation, optional professional profiles, community discussions, and privacy-conscious workplace insights.

> Your identity is optional. Your experiences matter.

---

## Project Overview

| Attribute               | Details                                                                     |
| ----------------------- | --------------------------------------------------------------------------- |
| Project                 | Pressure Out                                                                |
| Category                | Workplace Social Network                                                    |
| Development Stage       | Local Development & Qualification                                           |
| Implementation Coverage | Phases 1–12.3                                                               |
| Frontend                | Next.js, React, TypeScript                                                  |
| Backend                 | Python, FastAPI                                                             |
| Database                | PostgreSQL 16                                                               |
| Caching & Rate Limiting | Redis                                                                       |
| Localization            | English, Malayalam, Hindi, Tamil, Spanish                                   |
| Deployment Strategy     | Docker Compose / Windows Local Development                                  |
| Repository              | [BibinBinoy777/pressure-out](https://github.com/BibinBinoy777/pressure-out) |

**Current status:** The repository contains application code, architecture documentation, testing infrastructure and operational tooling through Phase 12.3. Production deployment has not yet been performed.

---

# 1. The Vision

Workplaces influence people's lives, careers, finances, relationships, and mental well-being. Yet many people hesitate to discuss their workplace experiences openly because of professional identity, organizational pressure, privacy concerns, or fear of consequences.

Pressure Out aims to change that.

The platform provides a digital space where people can:

* Express workplace frustrations without revealing their real identity.
* Share stories about toxic workplace environments and difficult experiences.
* Discuss salaries, career progression, management and professional challenges.
* Connect with people facing similar workplace situations.
* Share funny workplace moments, memes and office humour.
* Tell resignation stories and discuss reasons behind career transitions.
* Contribute to privacy-preserving aggregated workplace insights.

The guiding principle is simple:

**People should be able to discuss their professional lives without being forced to expose their personal identities.**

---

# 2. Core Product Principles

### 2.1 Privacy-First Identity

Pressure Out does not require users to publish under their real-world identity.

Users can choose their identity mode for individual posts:

* **Pseudonymous:** Participate using a public pseudonym.
* **Anonymous:** Share content anonymously within the community.
* **Professional:** Participate through an optional professional profile.

Identity selection is designed to support different participation needs without making real-world identity disclosure a requirement.

### 2.2 Freedom of Expression

The platform supports honest workplace conversations, including criticism, personal experiences, workplace humour and difficult professional situations.

Freedom of expression is balanced with moderation, privacy protection, reporting mechanisms and abuse-prevention safeguards.

### 2.3 Community Over Outrage

Feeds and discovery features are designed to encourage meaningful discussions rather than simply maximizing outrage or engagement.

### 2.4 Privacy-Preserving Insights

Aggregated workplace insights use consent-based contributions, minimum cohort thresholds and suppression rules to reduce the possibility of identifying individual contributors.

### 2.5 Technology for Human Expression

AI-assisted meme creation, multilingual support and content translation are intended to make workplace expression more accessible and engaging.

---

# 3. Key Features

## 3.1 Workplace Social Networking

Core social functionality includes:

* Creating workplace discussion posts.
* Sharing personal experiences and opinions.
* Community-based discussions.
* Comments and threaded conversations.
* Voting and reactions.
* Bookmarks and saved posts.
* Notifications and engagement features.
* Individual user profiles.
* Topic discovery and search.

## 3.2 Multiple Identity Modes

Users can select their preferred identity mode when publishing content.

The identity system supports:

* Pseudonymous participation.
* Anonymous participation.
* Optional professional profiles.
* Identity-aware content serialization.
* Privacy isolation between users.
* Anonymous author protection.
* Interaction restrictions and privacy controls.

## 3.3 Community System

Community functionality includes:

* Community discovery.
* Community membership.
* Community-specific discussions.
* Community rules.
* Moderation roles and permissions.
* Community-based content organization.

## 3.4 Intelligent Feeds and Discovery

The platform includes:

* Latest feed.
* Popular feed.
* Following feed.
* Explore and discovery.
* Topic following and muting.
* Search functionality.
* Saved searches and content preferences.
* Anti-outrage-oriented ranking mechanisms.

## 3.5 AI Meme Studio

The AI Meme Studio is one of Pressure Out's signature features.

It enables users to turn workplace experiences into memes and visual expressions.

Implemented capabilities include:

* Workplace meme templates.
* Caption editing.
* AI-assisted caption suggestions.
* Multilingual caption support.
* Image generation job management.
* Asynchronous job polling and cancellation.
* Meme previews.
* Alternative-text editing.
* Asset downloads.
* Community publishing.
* Identity-aware publishing.

The backend uses provider-neutral adapters for caption and image generation.

Local mock providers and disabled-provider configurations support development without requiring external AI API credentials.

The deterministic template renderer also supports locally generated workplace memes.

## 3.6 Trust, Safety and Moderation

Trust and safety functionality includes:

* Content reporting.
* Moderation queues.
* Moderation actions.
* Moderation appeals.
* User blocking and muting.
* Privacy-aware moderation views.
* Audit event recording.
* High-severity reporting safeguards.
* Abuse-prevention mechanisms.
* Separation of duties in moderation appeals.

The system is designed to protect users without unnecessarily exposing anonymous identities.

## 3.7 Multilingual Experience

The application includes five UI localization catalogs:

| Language  | Locale |
| --------- | ------ |
| English   | `en`   |
| Malayalam | `ml`   |
| Hindi     | `hi`   |
| Tamil     | `ta`   |
| Spanish   | `es`   |

Multilingual functionality includes:

* Externalized UI strings.
* Locale switching.
* Unicode normalization.
* Translation provider adapters.
* Post translation.
* Comment translation.
* Translation caching.
* Source-version-based cache invalidation.
* Preservation of original content.

The architecture is designed to support additional languages.

## 3.8 Workplace Experiences and Resignation Stories

Pressure Out includes dedicated features for sharing structured workplace experiences.

Implemented capabilities include:

* Workplace experience categories.
* Resignation stories.
* Structured resignation reasons.
* Optional workplace metadata.
* Multiple identity modes.
* Consent-based workplace contributions.
* Aggregated workplace statistics.

## 3.9 Privacy-Safe Workplace Insights

The workplace insights engine uses structured, consented contributions rather than treating public workplace narratives as automatically available statistical data.

Its safeguards include:

* Minimum cohort size of 10 for general metrics.
* Minimum cohort size of 20 for sensitive metrics.
* Complementary small-bucket suppression.
* Coarse sample-size banding.
* Limited simultaneous filter dimensions.
* No employer leaderboards.

These measures help reduce the risk of identifying individual contributors through aggregated information.

---

# 4. System Architecture

Pressure Out follows a modular application architecture.

### High-Level Architecture

```text
                    PRESSURE OUT
                          |
              +-----------+-----------+
              |                       |
         FRONTEND                 BACKEND
              |                       |
        Next.js / React           FastAPI
        TypeScript                    |
              |              +-------+-------+
              |              |       |       |
              |            API    Services  Workers
              |              |       |       |
              |              +-------+-------+
              |                      |
              |             +--------+--------+
              |             |                 |
              |         PostgreSQL           Redis
              |             |                 |
              |         SQLAlchemy       Rate Limiting
              |         Alembic           & Caching
              |                              
              +-------------------------------+
                          |
                   Storage Layer
                          |
                 Local / S3 / R2
```

### Architectural Components

**Frontend**

* Next.js App Router.
* React.
* TypeScript.
* Tailwind CSS.
* Externalized localization.
* Modular reusable components.

**Backend**

* FastAPI.
* Python.
* Pydantic.
* SQLAlchemy 2.x asynchronous database access.
* Alembic migrations.
* Modular domain services.
* Background workers.

**Database**

* PostgreSQL 16.
* Async SQLAlchemy.
* Database migrations.
* PostgreSQL extensions.
* Privacy-aware data relationships.

**Infrastructure**

* Docker Compose.
* Redis.
* Local filesystem storage.
* S3-compatible object storage adapters.
* Windows PowerShell development automation.

---

# 5. Technology Stack

| Layer                 | Technology                                |
| --------------------- | ----------------------------------------- |
| Frontend Framework    | Next.js                                   |
| UI Library            | React 19                                  |
| Programming Language  | TypeScript                                |
| Styling               | Tailwind CSS                              |
| Frontend Testing      | Node.js / Vitest / Custom VM verification |
| Backend Language      | Python 3.11 / 3.12                        |
| Backend Framework     | FastAPI                                   |
| Data Validation       | Pydantic                                  |
| ORM                   | SQLAlchemy 2.x                            |
| Database Migrations   | Alembic                                   |
| Database              | PostgreSQL 16                             |
| Database Extensions   | pgcrypto, citext, ltree, pg_trgm          |
| Cache / Rate Limiting | Redis                                     |
| Background Processing | Python Workers                            |
| Image Processing      | Pillow and HarfBuzz-compatible rendering  |
| Object Storage        | Local Filesystem / S3 / Cloudflare R2     |
| Containers            | Docker and Docker Compose                 |
| Backend Testing       | Pytest / unittest                         |
| Code Quality          | Ruff / ESLint / TypeScript                |

---

# 6. Repository Structure

```text
Pressure-Out/
|
|-- README.md
|-- .gitignore
|-- .env.example
|-- .env.local.example
|
|-- docker-compose.yml
|-- docker-compose.local.yml
|-- docker-compose.prod.yml
|
|-- backend/
|   |
|   |-- alembic/
|   |   |-- versions/
|   |   `-- env.py
|   |
|   |-- app/
|   |   |
|   |   |-- api/
|   |   |   `-- v1/
|   |   |
|   |   |-- core/
|   |   |-- database/
|   |   |-- middleware/
|   |   |
|   |   |-- modules/
|   |   |   |-- comments/
|   |   |   |-- communities/
|   |   |   |-- engagement/
|   |   |   |-- feed/
|   |   |   |-- identity/
|   |   |   |-- memes/
|   |   |   |-- moderation/
|   |   |   |-- notifications/
|   |   |   |-- posts/
|   |   |   |-- translations/
|   |   |   `-- workplace/
|   |   |
|   |   `-- workers/
|   |
|   |-- tests/
|   |-- Dockerfile
|   `-- pyproject.toml
|
|-- frontend/
|   |
|   |-- app/
|   |-- components/
|   |-- lib/
|   |-- locales/
|   |-- tests/
|   |-- Dockerfile
|   `-- package.json
|
|-- docs/
|   |
|   |-- architecture/
|   |-- decisions/
|   |-- development/
|   |-- diagrams/
|   |-- operations/
|   |-- product/
|   `-- roadmap/
|
|-- scripts/
|   |
|   |-- windows/
|   |-- backup_restore_postgres.sh
|   |-- performance_benchmark.py
|   |-- qualify_postgres_staging.py
|   `-- run_local_smoke_35.py
|
`-- storage/
    `-- media/
```

---

# 7. Getting Started

Pressure Out supports Docker Compose development and direct host development.

## 7.1 Prerequisites

### Recommended: Docker Workflow

* Docker Engine 24 or newer.
* Docker Compose v2 or newer.
* Git.

### Direct Host Development

* Python 3.11 or newer.
* Node.js 18.20+ or 20+.
* npm.
* PostgreSQL 16 or newer.
* Redis when using the Redis-backed local configuration.

## 7.2 Clone the Repository

```bash
git clone https://github.com/BibinBinoy777/pressure-out.git

cd pressure-out
```

## 7.3 Configure Environment Variables

For the standard Docker Compose development workflow:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Review the configuration before starting the application.

Important configuration categories include:

* Application environment.
* Database connection.
* Backend and frontend URLs.
* Redis configuration.
* Storage backend.
* AI provider settings.
* Translation provider settings.
* Meme generation limits.
* Logging configuration.

Development-only credentials must never be reused in production.

## 7.4 Start with Docker Compose

Build and start the development services:

```bash
docker compose up --build
```

Expected local endpoints:

| Service           | Address                             |
| ----------------- | ----------------------------------- |
| Frontend          | http://localhost:3000               |
| Backend           | http://localhost:8000               |
| Backend Health    | http://localhost:8000/api/v1/health |
| API Documentation | http://localhost:8000/api/v1/docs   |

The API documentation is available in development mode and is disabled in production configuration.

To stop the services:

```bash
docker compose down
```

This preserves the named PostgreSQL data volume.

**Warning:** Removing Docker volumes with `docker compose down -v` deletes the associated local database data.

## 7.5 Windows Local Development

For Windows 10/11 development, the repository includes a dedicated local configuration:

```text
docker-compose.local.yml
.env.local.example
scripts/windows/
docs/development/WINDOWS_LOCAL_DEVELOPMENT.md
```

This setup is designed to support local development under:

```text
D:\PressureOut
```

It includes configuration for:

* Local PostgreSQL 16.
* Redis 7 with `noeviction`.
* Configurable D: drive storage.
* Local dependency caches.
* PowerShell setup automation.
* Service startup and shutdown.
* Backend and frontend checks.
* Local end-to-end smoke verification.
* Backup and restore workflows.

Follow the complete Windows setup guide:

[`docs/development/WINDOWS_LOCAL_DEVELOPMENT.md`](docs/development/WINDOWS_LOCAL_DEVELOPMENT.md)

Available automation scripts are located in:

```text
scripts/windows/
```

---

# 8. Database Migrations

Pressure Out uses Alembic for PostgreSQL schema management.

From the backend directory:

```bash
cd backend
```

Apply migrations:

```bash
alembic upgrade head
```

Check the current migration:

```bash
alembic current
```

View migration history:

```bash
alembic history
```

The migration system establishes PostgreSQL extension prerequisites and introduces domain schemas through subsequent development phases.

---

# 9. Running Tests

The repository includes backend and frontend automated verification suites.

## 9.1 Backend

From `backend/`:

```bash
cd backend
```

Run unittest discovery:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -p "test_*.py" -v
```

Run Pytest:

```bash
pytest -v
```

Run Ruff:

```bash
ruff check .
```

## 9.2 Frontend

From `frontend/`:

```bash
cd frontend
```

Run the offline-capable verification suite:

```bash
npm run test:vm
```

Run standard frontend checks when dependencies are installed:

```bash
npm test
npm run typecheck
npm run lint
npm run build
```

## 9.3 End-to-End Local Qualification

The project includes a local smoke-test runner:

```text
scripts/run_local_smoke_35.py
```

Windows automation is available through:

```text
scripts/windows/run-local-smoke.ps1
```

Refer to the testing strategy and Windows development documentation for execution details.

---

# 10. Security and Privacy

Security and privacy are foundational design requirements of Pressure Out.

### Authentication and Identity

* Privacy-aware identity modes.
* Session and account security.
* Anonymous author protection.
* Account recovery safeguards.
* User data export.
* Account deletion lifecycle.

### Application Security

* Security response headers.
* Content Security Policy.
* CSRF trusted-origin enforcement.
* Request-size restrictions.
* Secure production startup validation.
* Credential redaction in application logs.
* Environment-based secret configuration.

### Rate Limiting

The backend supports:

* In-memory rate limiting.
* Redis-backed rate limiting.
* Atomic Redis Lua operations.
* Subject-key hashing.
* Bounded key expiration.
* Fail-closed behaviour when the configured Redis backend is unavailable.

Production configurations require Redis-backed rate limiting for multi-worker operation.

### Moderation and Abuse Prevention

* Reporting and appeals.
* High-severity reporting safeguards.
* User blocking and muting.
* Privacy-blind moderation workflows.
* Append-only moderation audit records.
* Separation of duties.

### Data Privacy

* Real-world identity is not required for public participation.
* Anonymous identity information is protected from ordinary community views.
* Workplace insights use consented structured contributions.
* Minimum aggregation thresholds protect sensitive statistical categories.
* Account deletion and export workflows are implemented in the identity module.

**Important:** Production credentials, encryption keys, database passwords and external API keys must be supplied through secure deployment configuration. Never commit actual secrets.

---

# 11. AI and External Provider Configuration

The AI Meme Studio and translation systems use provider-neutral adapters.

Supported architecture includes:

* Caption generation providers.
* Image generation providers.
* Translation providers.
* Local mock providers.
* Disabled-provider configurations.

The application can use its local development functionality without requiring external AI API credentials.

External provider integrations require their respective credentials and configuration.

Local mock providers are intended for development and testing, not production operation.

---

# 12. Development Roadmap and Implementation Progress

The repository documents the following development milestones.

| Phase      | Area                         | Implementation Scope                                                               |
| ---------- | ---------------------------- | ---------------------------------------------------------------------------------- |
| Phase 1    | Product & Architecture       | Product requirements, architecture, database design and specifications             |
| Phase 2    | Application Foundation       | Backend, frontend, database foundation, development setup and automated tests      |
| Phase 3    | Authentication & Privacy     | Accounts, identity modes, authentication and privacy isolation                     |
| Phase 4    | Social Posting               | Posts, publishing and social interaction foundations                               |
| Phase 5    | Communities                  | Community creation, membership and rules                                           |
| Phase 6    | Engagement                   | Comments, voting, reactions and notifications                                      |
| Phase 7    | Feeds & Discovery            | Latest, Popular, Following, Explore, ranking and search                            |
| Phase 8    | AI Meme Studio               | Templates, caption assistance, rendering and asynchronous generation workflows     |
| Phase 9    | Trust & Safety               | Reporting, moderation, appeals, blocking and muting                                |
| Phase 10   | Multilingual Experience      | Five locales, localization and content translation                                 |
| Phase 11   | Workplace Experiences        | Workplace stories, resignation reasons and privacy-safe aggregated insights        |
| Phase 12   | Production Hardening         | Security, performance, operational tooling and deployment qualification            |
| Phase 12.1 | Infrastructure Qualification | Redis-backed rate limiting, request limits and PostgreSQL qualification            |
| Phase 12.2 | Staging Qualification        | Redis eviction safeguards, networked qualification and object-storage verification |
| Phase 12.3 | Windows Local Development    | Windows setup, D: drive configuration and local smoke testing                      |

The repository contains source code, tests and documentation associated with these milestones.

Implementation presence and development qualification should not be interpreted as confirmation of a live production deployment.

---

# 13. Documentation

Detailed technical documentation is maintained under `docs/`.

| Directory            | Documentation                                                            |
| -------------------- | ------------------------------------------------------------------------ |
| `docs/product/`      | Product requirements, MVP scope, user journeys and acceptance criteria   |
| `docs/architecture/` | Frontend, backend, database, API, security, identity and AI architecture |
| `docs/decisions/`    | Architecture decision records                                            |
| `docs/diagrams/`     | System, database, identity and meme-generation diagrams                  |
| `docs/roadmap/`      | Development phases, risks and testing strategy                           |
| `docs/development/`  | Windows local development instructions                                   |
| `docs/operations/`   | Production readiness, operational procedures and runbooks                |

Some particularly useful documents:

* [Product Requirements](docs/product/PRODUCT_REQUIREMENTS.md)
* [System Architecture](docs/architecture/SYSTEM_ARCHITECTURE.md)
* [Database Design](docs/architecture/DATABASE_DESIGN.md)
* [API Specification](docs/architecture/API_SPECIFICATION.md)
* [Identity and Privacy](docs/architecture/IDENTITY_AND_PRIVACY.md)
* [AI Meme Studio](docs/architecture/AI_MEME_STUDIO.md)
* [Security and Moderation](docs/architecture/SECURITY_AND_MODERATION.md)
* [Multilingual Support](docs/architecture/MULTILINGUAL_SUPPORT.md)
* [Windows Local Development](docs/development/WINDOWS_LOCAL_DEVELOPMENT.md)
* [Production Readiness and Runbooks](docs/operations/PRODUCTION_READINESS_AND_RUNBOOKS.md)

---

# 14. Current Development Stage

Pressure Out is being developed and qualified locally before moving toward public deployment.

The current repository includes:

* A modular FastAPI backend.
* A Next.js frontend.
* PostgreSQL database migrations.
* Redis-backed infrastructure capabilities.
* Privacy-aware identity and social features.
* AI Meme Studio components.
* Trust and safety functionality.
* Five localization catalogs.
* Workplace experiences and aggregated insights.
* Docker Compose configurations.
* Windows development automation.
* Backup, restore and qualification tooling.
* Automated backend and frontend tests.

The production Compose configuration and operational documentation provide a foundation for future deployment planning.

**Production hosting, public service operation and production infrastructure qualification remain separate milestones.**

---

# 15. Future Direction

The broader vision is to evolve Pressure Out into a trusted global space for workplace expression and community-driven professional experiences.

Potential future directions include:

* Expanding language support.
* Improving AI-assisted creative tools.
* Enhancing workplace discussion and discovery.
* Improving community participation.
* Strengthening privacy and trust mechanisms.
* Expanding aggregated workplace intelligence.
* Completing deployment and operational qualification.
* Building a sustainable platform around workplace expression.

The long-term objective is to make workplace conversations more open, accessible and human without requiring people to compromise their privacy.

---

# 16. Project Repository

**GitHub:**
https://github.com/BibinBinoy777/pressure-out

**Primary Branch:** `main`

**Initial Release:** Pressure Out Phases 1–12.3

---

### Pressure Out

**Your Work. Your Chaos. Your People.**

*Work is serious. Talking about it doesn't have to be.*

A space to speak freely, share experiences, laugh together and make workplace conversations more human.
