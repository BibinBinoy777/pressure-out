# System Context & External Actors Diagram

**Document ID:** DIAG-PO-001  
**Related Spec:** [SYSTEM_ARCHITECTURE.md](../architecture/SYSTEM_ARCHITECTURE.md)

## 1. System Context Overview (Diagram 1)

This C4-style System Context diagram illustrates how external human actors and third-party infrastructure providers interact with the **Pressure Out Platform**, highlighting strict trust and privacy boundaries.

```mermaid
flowchart TB
    subgraph Actors["Human Actors"]
        Guest["Unauthenticated Visitor<br/>(Browses Public Feeds, Communities & Memes)"]
        Member["Registered Member<br/>(Posts as Pseudonym, Anonymous, or Professional;<br/>Uses AI Meme Studio)"]
        Moderator["Community / Platform Moderator<br/>(Reviews Reports, Enforces Rules,<br/>No Access to Private Auth Identity)"]
        Admin["System Administrator<br/>(Manages Infrastructure, Seeding &<br/>Audited Security Escalations)"]
    end

    subgraph PressureOutBoundary["Pressure Out System Boundary"]
        Edge["HTTPS Edge / Reverse Proxy<br/>(TLS Termination, WAF, Basic IP Rate Limits)"]
        CorePlatform["Pressure Out Core Platform<br/>(Next.js Web App + FastAPI Modular Monolith +<br/>PostgreSQL Source of Truth + Object Storage)"]
    end

    subgraph ExternalProviders["External Service Providers (Isolated Behind Server-Side Adapters)"]
        AIProvider["External AI Model Providers<br/>(Caption LLM & Image Gen APIs)<br/>*Receives Sanitized Prompt + Locale Only*"]
        TranslationProvider["Optional Translation Provider API<br/>(Derived Content Translation)<br/>*Receives Public Post Text + Target Locale Only*"]
        EmailProvider["Optional Transactional Email Provider<br/>(Account Recovery & Opt-in Alerts)<br/>*Used Only When User Supplies Recovery Email*"]
    end

    Guest -->|HTTPS GET Public Routes| Edge
    Member -->|HTTPS Authenticated Session + CSRF| Edge
    Moderator -->|HTTPS Role-Restricted Mod Routes| Edge
    Admin -->|HTTPS Audited Admin Routes + MFA| Edge

    Edge --> CorePlatform

    CorePlatform -->|Sanitized Prompt via Adapter<br/>Server-Side API Key, Quotas & Timeouts| AIProvider
    CorePlatform -.->|Optional Public Text via Adapter<br/>Non-Destructive Derived Variant| TranslationProvider
    CorePlatform -.->|Optional Recovery Token via Adapter| EmailProvider
```

## 2. Boundary Guarantees

1. **No Direct Browser-to-Provider Traffic:** User browsers never communicate directly with AI, translation, or email providers. All external provider keys remain strictly server-side inside the FastAPI backend/worker environment.
2. **Zero PII to AI Providers:** The `CaptionProviderAdapter` and `ImageProviderAdapter` strip all user account identifiers, session metadata, and IP addresses before dispatching generation prompts.
3. **Graceful External Independence:** Dashed links (`-.->`) indicate optional external capabilities. If `AIProvider`, `TranslationProvider`, or `EmailProvider` is unconfigured or offline, core community browsing, posting, commenting, and template meme creation continue uninterrupted.
