# Authentication, Public Identity & Anonymous Posting Flows

**Document ID:** DIAG-PO-004  
**Related Spec:** [IDENTITY_AND_PRIVACY.md](../architecture/IDENTITY_AND_PRIVACY.md)

## 1. Authentication & Three-Mode Identity Resolution Flow (Diagram 4)

This diagram illustrates how a single private account (`users.id`) authenticates once and dynamically selects between **Pseudonymous**, **Anonymous**, and **Professional** identity representations per post or comment.

```mermaid
sequenceDiagram
    autonumber
    actor User as Authenticated Member
    participant UI as Next.js Composer (IdentitySelector)
    participant API as FastAPI Post Service
    participant DB as PostgreSQL (users / profiles / posts)
    participant Serializer as PublicPostSerializer
    actor Reader as Other Community Reader

    User->>UI: Writes post & selects Identity Mode (Pseudonymous | Anonymous | Professional)
    UI->>API: POST /api/v1/posts (Cookie: session_id, X-CSRF-Token, identity_mode, body)
    API->>DB: Validate active session -> Resolve private user_id
    
    alt identity_mode == "pseudonymous"
        API->>DB: Verify public_profiles exists for user_id
        API->>DB: INSERT INTO posts (author_user_id=user_id, identity_mode='pseudonymous')
    else identity_mode == "anonymous"
        API->>DB: Run Pre-Publish PII Regex Check
        API->>DB: INSERT INTO posts (author_user_id=user_id, identity_mode='anonymous', anonymous_alias='Anonymous Member')
    else identity_mode == "professional"
        API->>DB: Fetch voluntary professional_profiles (role_title, industry, experience_band)
        API->>DB: INSERT INTO posts (author_user_id=user_id, identity_mode='professional', professional_snapshot=JSON)
    end

    Reader->>API: GET /api/v1/posts/{id}
    API->>DB: SELECT post + joined public_profile (if permitted)
    API->>Serializer: Serialize to PublicPostResponse

    alt post.identity_mode == "anonymous"
        Note over Serializer: STRIP author_user_id, handle, avatar, profile_id!<br/>Set author = { mode: "anonymous", label: "Anonymous Member" }
    else post.identity_mode == "pseudonymous"
        Note over Serializer: Set author = { mode: "pseudonymous", handle: "@handle", avatar_url: "..." }
    else post.identity_mode == "professional"
        Note over Serializer: Set author = { mode: "professional", handle: "@handle", badge: "Role • Industry • Exp" }
    end

    Serializer-->>Reader: 200 OK JSON (Zero Private Identity Leakage)
```

## 2. End-to-End Anonymous Posting, OP Reply & Moderation Boundary Flow (Diagram 5)

This flowchart shows how **Anonymous Posts** preserve private ownership for the author (editing, deleting, notifications, and sticky `Anonymous OP` replies) and enforce strict access boundaries for moderators.

```mermaid
flowchart TD
    subgraph AuthorActions["1. Author Creation & Ownership"]
        A[Author selects 'Anonymous' Mode in Composer] --> B[Pre-Publish PII Guard scans for Emails / Phones / Names]
        B -->|Warning Triggered| C[User edits text or acknowledges warning]
        B -->|Clean| D[FastAPI saves Post with private author_user_id + identity_mode='anonymous']
        C --> D
    end

    subgraph ThreadReply["2. Sticky Anonymous OP Reply Protection"]
        D --> E[Author opens their own Anonymous Post thread to reply]
        E --> F[Frontend & Backend detect current_user.id == post.author_user_id]
        F --> G[Comment Composer auto-locks to 'Anonymous OP']
        G --> H{Does Author try to switch to @handle?}
        H -->|No| I[Reply saved as 'Anonymous OP' — Zero Handle Exposure]
        H -->|Yes| J[Explicit Warning Modal: 'Revealing your handle here may link your profile to this anonymous post']
    end

    subgraph PublicSerialization["3. Public API Boundary"]
        D & I --> K[Public Serializer: PublicPostResponse / PublicCommentResponse]
        K --> L[Public Feed & Readers: See ONLY 'Anonymous Member' / 'Anonymous OP']
        K --> M[Author's Public Profile Page (/u/handle): Query filters WHERE identity_mode != 'anonymous']
    end

    subgraph ModerationBoundary["4. Least-Privilege Moderation Boundary"]
        L --> N[Post Reported by Community Member]
        N --> O[Moderation Queue View (/moderation/queue)]
        O --> P[Moderator sees Post Text, Report Reason & Prior Restricted Action Count]
        P --> Q[Moderator NEVER sees author_user_id, @handle, email, or IP]
        Q --> R[Moderator applies Action -> Recorded in append-only audit_events]
    end
```
