# System Components & Deployment Topology Diagrams

**Document ID:** DIAG-PO-002  
**Related Specs:** [SYSTEM_ARCHITECTURE.md](../architecture/SYSTEM_ARCHITECTURE.md), [DEPLOYMENT_AND_OPERATIONS.md](../architecture/DEPLOYMENT_AND_OPERATIONS.md)

## 1. Internal Component Architecture (Diagram 2)

This diagram illustrates the internal component boundaries across the **Next.js Frontend**, the **FastAPI Modular Monolith**, the **PostgreSQL Database**, **Object Storage**, and the **Asynchronous Background Worker**.

```mermaid
flowchart TB
    subgraph ClientBrowser["Client Browser (Desktop & Mobile Web)"]
        NextSSR["Next.js App Router (SSR Public Pages)"]
        ReactCSR["React Interactive Client Components<br/>(Composer, IdentitySelector, MemeEditor, ModQueue)"]
        APIClient["Typed REST Client (/api/v1)<br/>+ Locale Resource Loader"]
    end

    subgraph FastAPIMonolith["FastAPI Modular Monolith (Backend API Process)"]
        RouterLayer["API v1 Routers & Public Response Serializers<br/>(Enforces Anonymous Identity Stripping)"]
        AuthMiddleware["Session Auth, CSRF Guard, RBAC & Rate Limiter"]
        
        subgraph DomainModules["Internal Domain Modules"]
            ModIdentity["identity<br/>(Accounts, Sessions, Profiles)"]
            ModPosts["posts<br/>(Posts, Comments, Polls, Votes, Exit Stories)"]
            ModComm["communities<br/>(Spaces, Memberships, Rules)"]
            ModFeed["feed<br/>(Latest, Popular, Following, FTS Search)"]
            ModMemes["memes<br/>(Template Renderer, Job Orchestrator)"]
            ModLang["languages<br/>(BCP 47 Tags, Derived Translations)"]
            ModSafety["moderation<br/>(PII Guard, Reports, Queue, Audit Log)"]
            ModNotif["notifications<br/>(In-App Alerts)"]
        end

        subgraph AdapterBoundary["External Service Adapters"]
            AIAdapter["AI Provider Adapter<br/>(Caption & Image Interfaces)"]
            StorageAdapter["Media Storage Adapter<br/>(Signed URLs & Asset Validation)"]
            TransAdapter["Translation Adapter"]
        end
    end

    subgraph WorkerProcess["Background Worker Process (Same Codebase)"]
        JobPoller["PostgreSQL SKIP LOCKED Job Consumer<br/>(AI Meme Jobs, Derived Translations, Media Cleanup)"]
    end

    subgraph DataAndStorage["Persistence & Media Layer"]
        Postgres[("PostgreSQL 16+ (Source of Truth)<br/>Relational Tables + GIN FTS + ltree + Job Queue")]
        ObjStore[("Private Object Storage<br/>(Templates, Rendered Memes, Generated Assets)")]
    end

    NextSSR & ReactCSR --> APIClient
    APIClient -->|HTTPS JSON + HttpOnly Cookie| AuthMiddleware
    AuthMiddleware --> RouterLayer
    RouterLayer --> ModIdentity & ModPosts & ModComm & ModFeed & ModMemes & ModLang & ModSafety & ModNotif

    ModMemes --> AIAdapter & StorageAdapter
    ModLang --> TransAdapter
    ModIdentity & ModPosts & ModComm & ModFeed & ModMemes & ModLang & ModSafety & ModNotif -->|Async SQLAlchemy 2.0 Transactions| Postgres
    StorageAdapter --> ObjStore

    JobPoller -->|Polls meme_jobs & background_tasks| Postgres
    JobPoller --> AIAdapter & StorageAdapter & TransAdapter
```

## 2. Deployment Architecture Across Environments (Diagram 7)

This diagram contrasts the **Local Development Environment** (zero external cloud dependencies) with the **Target Production Topology** (defense-in-depth, private network boundaries, and automated backups).

```mermaid
flowchart TB
    subgraph LocalDev["Local Development Environment (Docker Compose)"]
        DevBrowser["Developer Browser (localhost:3000)"]
        DevNext["Next.js Dev Server (:3000)"]
        DevFastAPI["FastAPI Backend (:8000)"]
        DevWorker["FastAPI Worker Process"]
        DevPG[("Local PostgreSQL 16 (:5432)<br/>Sample Seed Data Only")]
        DevFS[("Local Volume (./storage/media)<br/>+ LocalMockAIProvider")]

        DevBrowser --> DevNext
        DevNext --> DevFastAPI
        DevFastAPI --> DevPG & DevFS
        DevWorker --> DevPG & DevFS
    end

    subgraph ProdEnv["Target Production Topology (When Launch Gates Pass)"]
        Users["Public Internet Users"]
        EdgeCDN["DNS + HTTPS + CDN / WAF<br/>(TLS 1.3, DDoS & Edge Rate Limiting)"]

        subgraph PublicDMZ["Application Tier"]
            ProdNext["Managed Next.js / Container Service"]
            ProdAPI["FastAPI API Containers<br/>(Stateless, Horizontal Auto-Scale)"]
        end

        subgraph PrivateVPC["Private Network Boundary (No Public Ingress)"]
            ProdWorker["Background Worker Containers<br/>(AI Jobs, Translations, Cleanup)"]
            ProdPG[("Managed PostgreSQL 16+<br/>Encrypted at Rest, Least-Privilege Role")]
            ProdS3[("Private Object Storage (S3/R2)<br/>Controlled Signed URLs")]
            ProdBackups[("Encrypted Offsite Backups<br/>+ Periodic Restore Verification")]
            ProdObs["Observability & Alerting<br/>(Redacted Structured Logs, Metrics, Cost Alerts)"]
        end

        Users -->|HTTPS| EdgeCDN
        EdgeCDN --> ProdNext & ProdAPI
        ProdNext --> ProdAPI
        ProdAPI --> ProdPG & ProdS3 & ProdObs
        ProdWorker --> ProdPG & ProdS3 & ProdObs
        ProdPG --> ProdBackups
    end
```
