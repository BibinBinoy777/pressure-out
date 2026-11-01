/**
 * Reusable HTTP client for communicating with the FastAPI `/api/v1` backend (Phases 2 & 3).
 *
 * Handles:
 * - Configurable base URLs (browser vs. SSR container network)
 * - Automatic credentials ('include') for HttpOnly session cookies
 * - Automatic `X-CSRF-Token` header attachment on state-changing requests
 * - Safe user-facing failure messages without leaking internal server details
 */
import { resolveApiBaseUrl } from "./config";
import { translate } from "./i18n";

export type IdentityMode = "pseudonymous" | "anonymous" | "professional";

export type ExperienceBand =
  | "fresher_0_1"
  | "junior_1_3"
  | "mid_3_6"
  | "senior_6_10"
  | "lead_10_plus";

export interface HealthApiResponse {
  status: "ok";
  service: string;
  api_version: string;
}

export interface VoluntaryProfessionalBadge {
  role_title: string;
  industry: string;
  experience_band: ExperienceBand;
  region_label?: string | null;
  is_verified: boolean;
}

export interface PublicProfileResponse {
  handle: string;
  display_name?: string | null;
  bio?: string | null;
  avatar_url?: string | null;
  show_karma: boolean;
  professional_badge?: VoluntaryProfessionalBadge | null;
  created_at: string;
}

export interface PublicAuthorDisplay {
  identity_mode: IdentityMode;
  display_name: string;
  handle?: string | null;
  avatar_url?: string | null;
  professional_badge?: VoluntaryProfessionalBadge | null;
  is_anonymous_op: boolean;
}

export interface PrivateProfessionalProfile {
  role_title: string;
  industry: string;
  experience_band: ExperienceBand;
  region_label?: string | null;
  is_enabled: boolean;
  is_verified: boolean;
}

export interface PrivateAccountResponse {
  user_id: string;
  handle: string;
  display_name?: string | null;
  bio?: string | null;
  show_karma: boolean;
  account_status: string;
  role: string;
  default_identity_mode: IdentityMode;
  preferred_ui_locale: string;
  preferred_content_locales: string[];
  has_recovery_email: boolean;
  masked_recovery_email?: string | null;
  professional_profile?: PrivateProfessionalProfile | null;
  csrf_token?: string | null;
  one_time_recovery_code?: string | null;
  created_at: string;
}

export interface ApiErrorInfo {
  code: string;
  message: string;
  correlationId?: string;
}

export type ApiResult<T> =
  | { ok: true; data: T; correlationId?: string }
  | { ok: false; error: ApiErrorInfo };

export interface RequestOptions {
  baseUrl?: string;
  timeoutMs?: number;
  csrfToken?: string;
  headers?: Record<string, string>;
  fetchImpl?: typeof fetch;
}

function isValidHealthPayload(value: unknown): value is HealthApiResponse {
  if (value === null || typeof value !== "object") {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    candidate.status === "ok" &&
    typeof candidate.service === "string" &&
    candidate.service.length > 0 &&
    typeof candidate.api_version === "string" &&
    candidate.api_version.length > 0
  );
}

export async function apiRequest<T>(
  path: string,
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  body?: unknown,
  options: RequestOptions = {}
): Promise<ApiResult<T>> {
  const baseUrl = (options.baseUrl ?? resolveApiBaseUrl()).replace(/\/+$/, "");
  const timeoutMs = options.timeoutMs ?? 5000;
  const fetchFn = options.fetchImpl ?? globalThis.fetch;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const reqHeaders: Record<string, string> = {
    Accept: "application/json",
    ...(options.headers || {}),
  };

  if (body !== undefined) {
    reqHeaders["Content-Type"] = "application/json";
  }
  if (options.csrfToken) {
    reqHeaders["X-CSRF-Token"] = options.csrfToken;
  }

  try {
    const response = await fetchFn(`${baseUrl}${path}`, {
      method,
      headers: reqHeaders,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      credentials: "include",
      signal: controller.signal,
      cache: "no-store",
    });

    const correlationId =
      response.headers?.get?.("X-Correlation-ID") ??
      response.headers?.get?.("x-correlation-id") ??
      undefined;

    let parsedBody: unknown;
    try {
      parsedBody = await response.json();
    } catch {
      return {
        ok: false,
        error: {
          code: "UNEXPECTED_RESPONSE_FORMAT",
          message: translate("status.unexpectedFormatMessage"),
          correlationId,
        },
      };
    }

    if (!response.ok) {
      const errObj =
        parsedBody !== null &&
        typeof parsedBody === "object" &&
        "error" in (parsedBody as Record<string, unknown>)
          ? ((parsedBody as Record<string, unknown>).error as Record<string, unknown>)
          : undefined;

      const safeCode =
        typeof errObj?.code === "string" ? errObj.code : `HTTP_${response.status}`;
      const safeMessage =
        typeof errObj?.message === "string"
          ? errObj.message
          : translate("status.offlineFallbackMessage");

      return {
        ok: false,
        error: {
          code: safeCode,
          message: safeMessage,
          correlationId:
            typeof errObj?.correlation_id === "string"
              ? errObj.correlation_id
              : correlationId,
        },
      };
    }

    return {
      ok: true,
      data: parsedBody as T,
      correlationId,
    };
  } catch (err: unknown) {
    const isAbort =
      err instanceof Error &&
      (err.name === "AbortError" || err.message.toLowerCase().includes("abort"));

    if (isAbort) {
      return {
        ok: false,
        error: {
          code: "REQUEST_TIMEOUT",
          message: translate("status.timeoutMessage"),
        },
      };
    }

    return {
      ok: false,
      error: {
        code: "BACKEND_UNAVAILABLE",
        message: translate("status.offlineFallbackMessage"),
      },
    };
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchBackendHealth(
  options: RequestOptions = {}
): Promise<ApiResult<HealthApiResponse>> {
  const result = await apiRequest<unknown>("/api/v1/health", "GET", undefined, options);
  if (!result.ok) {
    return result;
  }
  if (!isValidHealthPayload(result.data)) {
    return {
      ok: false,
      error: {
        code: "UNEXPECTED_RESPONSE_FORMAT",
        message: translate("status.unexpectedFormatMessage"),
        correlationId: result.correlationId,
      },
    };
  }
  return {
    ok: true,
    data: result.data,
    correlationId: result.correlationId,
  };
}

export async function registerAccount(
  payload: {
    handle: string;
    password: string;
    recovery_email?: string | null;
    preferred_ui_locale?: string;
  },
  options: RequestOptions = {}
): Promise<ApiResult<PrivateAccountResponse>> {
  return apiRequest<PrivateAccountResponse>("/api/v1/auth/register", "POST", payload, options);
}

export async function loginAccount(
  payload: { handle: string; password: string },
  options: RequestOptions = {}
): Promise<ApiResult<PrivateAccountResponse>> {
  return apiRequest<PrivateAccountResponse>("/api/v1/auth/login", "POST", payload, options);
}

export async function logoutAccount(
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<{ status: string }>> {
  return apiRequest<{ status: string }>("/api/v1/auth/logout", "POST", undefined, {
    ...options,
    csrfToken,
  });
}

export async function fetchCurrentAccount(
  options: RequestOptions = {}
): Promise<ApiResult<PrivateAccountResponse>> {
  return apiRequest<PrivateAccountResponse>("/api/v1/me", "GET", undefined, options);
}

export async function updateMyProfile(
  payload: {
    display_name?: string | null;
    bio?: string | null;
    show_karma?: boolean;
    professional_profile?: {
      role_title: string;
      industry: string;
      experience_band: ExperienceBand;
      region_label?: string | null;
      is_enabled: boolean;
    } | null;
  },
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<PrivateAccountResponse>> {
  return apiRequest<PrivateAccountResponse>("/api/v1/me/profile", "PATCH", payload, {
    ...options,
    csrfToken,
  });
}

export async function updateMySettings(
  payload: {
    default_identity_mode?: IdentityMode;
    preferred_ui_locale?: string;
    preferred_content_locales?: string[];
    recovery_email?: string | null;
  },
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<PrivateAccountResponse>> {
  return apiRequest<PrivateAccountResponse>("/api/v1/me/settings", "PATCH", payload, {
    ...options,
    csrfToken,
  });
}

export async function deleteMyAccount(
  payload: { password_confirmation: string; delete_published_posts?: boolean },
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<{ status: string }>> {
  return apiRequest<{ status: string }>("/api/v1/me", "DELETE", payload, {
    ...options,
    csrfToken,
  });
}

export async function fetchPublicProfile(
  handle: string,
  options: RequestOptions = {}
): Promise<ApiResult<PublicProfileResponse>> {
  return apiRequest<PublicProfileResponse>(
    `/api/v1/profiles/${encodeURIComponent(handle)}`,
    "GET",
    undefined,
    options
  );
}


export type PostType =
  | "discussion"
  | "question"
  | "rant"
  | "story"
  | "meme"
  | "poll"
  | "advice_request"
  | "workplace_experience";

export interface PollOptionResponse {
  id: string;
  position: number;
  option_text: string;
  vote_count: number;
  percentage: number;
}

export interface PublicPollResponse {
  allows_multiple: boolean;
  total_votes: number;
  options: PollOptionResponse[];
  viewer_selected_option_ids: string[];
}

export interface PostStatsResponse {
  score: number;
  upvote_count: number;
  downvote_count: number;
  comment_count: number;
  reaction_counts: Record<string, number>;
}

export interface PostViewerContext {
  is_author: boolean;
  can_edit: boolean;
  can_delete: boolean;
}

export interface PiiWarningItem {
  category: string;
  severity: string;
  message: string;
  suggestion: string;
}

export interface PublicPostResponse {
  id: string;
  community: {
    slug: string;
    name: string;
  };
  post_type: PostType;
  identity_mode: IdentityMode;
  author: PublicAuthorDisplay;
  title: string;
  body: string;
  content_language: string;
  tags: string[];
  meme_asset_id?: string | null;
  meme_asset?: PublicMemeAssetSummary | null;
  workplace_detail?: PublicWorkplaceDetailSummary | null;
  poll?: PublicPollResponse | null;
  stats: PostStatsResponse;
  viewer_context: PostViewerContext;
  pii_warnings: PiiWarningItem[];
  created_at: string;
  updated_at: string;
}

export interface CursorPostListResponse {
  items: PublicPostResponse[];
  next_cursor?: string | null;
  has_more: boolean;
}

export async function createPost(
  payload: {
    community_slug?: string;
    post_type: PostType;
    identity_mode: IdentityMode;
    title: string;
    body: string;
    content_language?: string;
    tags?: string[];
    poll?: { options: string[]; allows_multiple?: boolean } | null;
    meme_asset_id?: string | null;
  meme_asset?: PublicMemeAssetSummary | null;
  workplace_detail?: PublicWorkplaceDetailSummary | null;
    acknowledge_pii_warning?: boolean;
  },
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<PublicPostResponse>> {
  return apiRequest<PublicPostResponse>("/api/v1/posts", "POST", payload, {
    ...options,
    csrfToken,
  });
}

export async function fetchPosts(
  params: {
    community_slug?: string;
    post_type?: PostType;
    tag?: string;
    lang?: string;
    cursor?: string;
    limit?: number;
  } = {},
  options: RequestOptions = {}
): Promise<ApiResult<CursorPostListResponse>> {
  const search = new URLSearchParams();
  if (params.community_slug) search.set("community_slug", params.community_slug);
  if (params.post_type) search.set("post_type", params.post_type);
  if (params.tag) search.set("tag", params.tag);
  if (params.lang) search.set("lang", params.lang);
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit) search.set("limit", String(params.limit));
  const qs = search.toString();
  return apiRequest<CursorPostListResponse>(
    `/api/v1/posts${qs ? `?${qs}` : ""}`,
    "GET",
    undefined,
    options
  );
}

export async function fetchPostById(
  postId: string,
  options: RequestOptions = {}
): Promise<ApiResult<PublicPostResponse>> {
  return apiRequest<PublicPostResponse>(
    `/api/v1/posts/${encodeURIComponent(postId)}`,
    "GET",
    undefined,
    options
  );
}

export async function updatePost(
  postId: string,
  payload: {
    title?: string;
    body?: string;
    identity_mode?: IdentityMode;
    content_language?: string;
    tags?: string[];
    acknowledge_pii_warning?: boolean;
  },
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<PublicPostResponse>> {
  return apiRequest<PublicPostResponse>(
    `/api/v1/posts/${encodeURIComponent(postId)}`,
    "PATCH",
    payload,
    { ...options, csrfToken }
  );
}

export async function deletePost(
  postId: string,
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<{ status: string; id: string }>> {
  return apiRequest<{ status: string; id: string }>(
    `/api/v1/posts/${encodeURIComponent(postId)}`,
    "DELETE",
    undefined,
    { ...options, csrfToken }
  );
}

export async function voteOnPoll(
  postId: string,
  optionIds: string[],
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<PublicPollResponse>> {
  return apiRequest<PublicPollResponse>(
    `/api/v1/posts/${encodeURIComponent(postId)}/poll/vote`,
    "POST",
    { option_ids: optionIds },
    { ...options, csrfToken }
  );
}

export async function fetchProfilePosts(
  handle: string,
  cursor?: string,
  options: RequestOptions = {}
): Promise<ApiResult<CursorPostListResponse>> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiRequest<CursorPostListResponse>(
    `/api/v1/profiles/${encodeURIComponent(handle)}/posts${qs}`,
    "GET",
    undefined,
    options
  );
}


export interface CommunityRuleResponse {
  rule_number: number;
  title: string;
  description: string;
}

export interface CommunityViewerContext {
  is_member: boolean;
  role?: string | null;
  is_banned: boolean;
  can_post: boolean;
  can_moderate: boolean;
}

export interface CommunitySummaryResponse {
  id: string;
  slug: string;
  name: string;
  description: string;
  icon_name?: string | null;
  primary_language: string;
  status: "active" | "restricted" | "archived";
  member_count: number;
  post_count: number;
  viewer_context: CommunityViewerContext;
}

export interface CommunityDetailResponse extends CommunitySummaryResponse {
  rules: CommunityRuleResponse[];
  created_at: string;
}

export interface MembershipActionResponse {
  community_slug: string;
  is_member: boolean;
  role?: string | null;
  member_count: number;
}

export async function fetchCommunities(
  params: { q?: string; lang?: string; joined_only?: boolean } = {},
  options: RequestOptions = {}
): Promise<ApiResult<CommunitySummaryResponse[]>> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.lang) search.set("lang", params.lang);
  if (params.joined_only) search.set("joined_only", "true");
  const qs = search.toString();
  return apiRequest<CommunitySummaryResponse[]>(
    `/api/v1/communities${qs ? `?${qs}` : ""}`,
    "GET",
    undefined,
    options
  );
}

export async function fetchCommunityBySlug(
  slug: string,
  options: RequestOptions = {}
): Promise<ApiResult<CommunityDetailResponse>> {
  return apiRequest<CommunityDetailResponse>(
    `/api/v1/communities/${encodeURIComponent(slug)}`,
    "GET",
    undefined,
    options
  );
}

export async function updateCommunityMembership(
  slug: string,
  action: "join" | "leave",
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<MembershipActionResponse>> {
  return apiRequest<MembershipActionResponse>(
    `/api/v1/communities/${encodeURIComponent(slug)}/membership`,
    "POST",
    { action },
    { ...options, csrfToken }
  );
}

export async function fetchCommunityFeed(
  slug: string,
  params: { post_type?: PostType; tag?: string; lang?: string; cursor?: string; limit?: number } = {},
  options: RequestOptions = {}
): Promise<ApiResult<CursorPostListResponse>> {
  const search = new URLSearchParams();
  if (params.post_type) search.set("post_type", params.post_type);
  if (params.tag) search.set("tag", params.tag);
  if (params.lang) search.set("lang", params.lang);
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit) search.set("limit", String(params.limit));
  const qs = search.toString();
  return apiRequest<CursorPostListResponse>(
    `/api/v1/communities/${encodeURIComponent(slug)}/posts${qs ? `?${qs}` : ""}`,
    "GET",
    undefined,
    options
  );
}


export type ReactionKind = "relatable" | "laugh" | "support" | "oof" | "respect";

export interface VoteResultResponse {
  target_type: "post" | "comment";
  target_id: string;
  score: number;
  upvote_count: number;
  downvote_count: number;
  viewer_vote: number;
}

export interface ReactionResultResponse {
  target_type: "post" | "comment";
  target_id: string;
  reaction_counts: Record<string, number>;
  viewer_reactions: ReactionKind[];
}

export interface SavePostResponse {
  post_id: string;
  saved: boolean;
}

export interface CommentStatsResponse {
  score: number;
  upvote_count: number;
  downvote_count: number;
  reaction_counts: Record<string, number>;
}

export interface CommentViewerContext {
  is_author: boolean;
  can_edit: boolean;
  can_delete: boolean;
  viewer_vote: number;
  viewer_reactions: string[];
}

export interface PublicCommentResponse {
  id: string;
  post_id: string;
  parent_comment_id?: string | null;
  path: string;
  depth: number;
  identity_mode: IdentityMode;
  author: PublicAuthorDisplay;
  body: string;
  content_language: string;
  is_deleted: boolean;
  stats: CommentStatsResponse;
  viewer_context: CommentViewerContext;
  pii_warnings: PiiWarningItem[];
  created_at: string;
  updated_at: string;
}

export interface CursorCommentListResponse {
  items: PublicCommentResponse[];
  next_cursor?: string | null;
  has_more: boolean;
}

export interface NotificationResponse {
  id: string;
  notification_type: string;
  reference_type: string;
  reference_id: string;
  title: string;
  body_preview?: string | null;
  is_read: boolean;
  created_at: string;
}

export interface CursorNotificationListResponse {
  items: NotificationResponse[];
  unread_count: number;
  next_cursor?: string | null;
  has_more: boolean;
}

export async function voteOnPost(
  postId: string,
  value: 1 | -1 | 0,
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<VoteResultResponse>> {
  return apiRequest<VoteResultResponse>(
    `/api/v1/posts/${encodeURIComponent(postId)}/vote`,
    "PUT",
    { value },
    { ...options, csrfToken }
  );
}

export async function togglePostReaction(
  postId: string,
  kind: ReactionKind,
  active: boolean,
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<ReactionResultResponse>> {
  return apiRequest<ReactionResultResponse>(
    `/api/v1/posts/${encodeURIComponent(postId)}/reactions/${encodeURIComponent(kind)}`,
    "PUT",
    { active },
    { ...options, csrfToken }
  );
}

export async function savePost(
  postId: string,
  saved: boolean,
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<SavePostResponse>> {
  return apiRequest<SavePostResponse>(
    `/api/v1/posts/${encodeURIComponent(postId)}/save`,
    "POST",
    { saved },
    { ...options, csrfToken }
  );
}

export async function fetchSavedPosts(
  cursor?: string,
  options: RequestOptions = {}
): Promise<ApiResult<CursorPostListResponse>> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiRequest<CursorPostListResponse>(`/api/v1/me/saved${qs}`, "GET", undefined, options);
}

export async function fetchPostComments(
  postId: string,
  params: { parent_id?: string; cursor?: string; limit?: number } = {},
  options: RequestOptions = {}
): Promise<ApiResult<CursorCommentListResponse>> {
  const search = new URLSearchParams();
  if (params.parent_id) search.set("parent_id", params.parent_id);
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit) search.set("limit", String(params.limit));
  const qs = search.toString();
  return apiRequest<CursorCommentListResponse>(
    `/api/v1/posts/${encodeURIComponent(postId)}/comments${qs ? `?${qs}` : ""}`,
    "GET",
    undefined,
    options
  );
}

export async function createPostComment(
  postId: string,
  payload: {
    parent_comment_id?: string | null;
    body: string;
    identity_mode?: IdentityMode | null;
    confirm_op_identity_reveal?: boolean;
    content_language?: string;
    acknowledge_pii_warning?: boolean;
  },
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<PublicCommentResponse>> {
  return apiRequest<PublicCommentResponse>(
    `/api/v1/posts/${encodeURIComponent(postId)}/comments`,
    "POST",
    payload,
    { ...options, csrfToken }
  );
}

export async function updateComment(
  commentId: string,
  body: string,
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<PublicCommentResponse>> {
  return apiRequest<PublicCommentResponse>(
    `/api/v1/comments/${encodeURIComponent(commentId)}`,
    "PATCH",
    { body },
    { ...options, csrfToken }
  );
}

export async function deleteComment(
  commentId: string,
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<{ status: string; id: string }>> {
  return apiRequest<{ status: string; id: string }>(
    `/api/v1/comments/${encodeURIComponent(commentId)}`,
    "DELETE",
    undefined,
    { ...options, csrfToken }
  );
}

export async function voteOnComment(
  commentId: string,
  value: 1 | -1 | 0,
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<VoteResultResponse>> {
  return apiRequest<VoteResultResponse>(
    `/api/v1/comments/${encodeURIComponent(commentId)}/vote`,
    "PUT",
    { value },
    { ...options, csrfToken }
  );
}

export async function fetchNotifications(
  params: { unread_only?: boolean; cursor?: string } = {},
  options: RequestOptions = {}
): Promise<ApiResult<CursorNotificationListResponse>> {
  const search = new URLSearchParams();
  if (params.unread_only) search.set("unread_only", "true");
  if (params.cursor) search.set("cursor", params.cursor);
  const qs = search.toString();
  return apiRequest<CursorNotificationListResponse>(
    `/api/v1/notifications${qs ? `?${qs}` : ""}`,
    "GET",
    undefined,
    options
  );
}

export async function markNotificationsRead(
  payload: { notification_ids?: string[]; mark_all?: boolean },
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<{ updated_count: number }>> {
  return apiRequest<{ updated_count: number }>(
    "/api/v1/notifications/read",
    "PATCH",
    payload,
    { ...options, csrfToken }
  );
}


export type FeedMode = "latest" | "popular" | "following" | "explore";

export interface TrendingTagItem {
  slug: string;
  display_name: string;
  usage_count: number;
  viewer_preference?: "follow" | "mute" | null;
}

export interface ExploreDiscoveryResponse {
  trending_tags: TrendingTagItem[];
  featured_communities: CommunitySummaryResponse[];
  fresh_community_posts: PublicPostResponse[];
  popular_posts: PublicPostResponse[];
}

export interface TopicPreferenceResponse {
  tag_slug: string;
  preference: "follow" | "mute" | "none";
}

export async function fetchFeed(
  params: {
    mode?: FeedMode;
    community_slug?: string;
    post_type?: PostType;
    tag?: string;
    lang?: string;
    cursor?: string;
    limit?: number;
  } = {},
  options: RequestOptions = {}
): Promise<ApiResult<CursorPostListResponse>> {
  const search = new URLSearchParams();
  if (params.mode) search.set("mode", params.mode);
  if (params.community_slug) search.set("community_slug", params.community_slug);
  if (params.post_type) search.set("post_type", params.post_type);
  if (params.tag) search.set("tag", params.tag);
  if (params.lang) search.set("lang", params.lang);
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit) search.set("limit", String(params.limit));
  const qs = search.toString();
  return apiRequest<CursorPostListResponse>(
    `/api/v1/feed${qs ? `?${qs}` : ""}`,
    "GET",
    undefined,
    options
  );
}

export async function fetchExploreDiscovery(
  lang?: string,
  options: RequestOptions = {}
): Promise<ApiResult<ExploreDiscoveryResponse>> {
  const qs = lang ? `?lang=${encodeURIComponent(lang)}` : "";
  return apiRequest<ExploreDiscoveryResponse>(`/api/v1/explore${qs}`, "GET", undefined, options);
}

export async function updateTopicPreference(
  tagSlug: string,
  preference: "follow" | "mute" | "none",
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<TopicPreferenceResponse>> {
  return apiRequest<TopicPreferenceResponse>(
    `/api/v1/feed/topics/${encodeURIComponent(tagSlug)}`,
    "PUT",
    { preference },
    { ...options, csrfToken }
  );
}

export async function searchPosts(
  params: {
    q: string;
    community_slug?: string;
    post_type?: PostType;
    tag?: string;
    lang?: string;
    cursor?: string;
    limit?: number;
  },
  options: RequestOptions = {}
): Promise<ApiResult<CursorPostListResponse>> {
  const search = new URLSearchParams();
  search.set("q", params.q);
  if (params.community_slug) search.set("community_slug", params.community_slug);
  if (params.post_type) search.set("post_type", params.post_type);
  if (params.tag) search.set("tag", params.tag);
  if (params.lang) search.set("lang", params.lang);
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit) search.set("limit", String(params.limit));
  return apiRequest<CursorPostListResponse>(
    `/api/v1/search?${search.toString()}`,
    "GET",
    undefined,
    options
  );
}

export interface PublicMemeAssetSummary {
  id: string;
  source_type: string;
  mime_type: string;
  width: number;
  height: number;
  alt_text: string;
  caption_language: string;
  download_url: string;
}

export interface MemeTextRegion {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  align: "left" | "center" | "right";
  max_chars: number;
  default_font_size: number;
  min_font_size: number;
}

export interface MemeTemplateResponse {
  id: string;
  slug: string;
  name: string;
  description: string;
  category: string;
  width: number;
  height: number;
  aspect_ratio: string;
  text_regions: MemeTextRegion[];
  default_typography: Record<string, unknown>;
  default_alt_text: string;
  category_tags: string[];
  license_info: string;
  preview_url: string;
}

export interface MemeTemplateListResponse {
  items: MemeTemplateResponse[];
  ai_caption_enabled: boolean;
  ai_image_enabled: boolean;
  is_mock_provider: boolean;
}

export interface CaptionRegionInput {
  region_id: string;
  text: string;
  align?: "left" | "center" | "right";
  font_size_override?: number;
}

export interface MemeAssetResponse {
  id: string;
  source_type: string;
  template_id?: string | null;
  mime_type: string;
  file_size_bytes: number;
  sha256_hash: string;
  width: number;
  height: number;
  captions: Array<{ region_id: string; text: string }>;
  caption_language: string;
  alt_text: string;
  safety_status: string;
  is_published: boolean;
  download_url: string;
  created_at: string;
}

export interface CaptionSuggestionItem {
  top_text: string;
  bottom_text: string;
  tone: string;
  language: string;
}

export interface SuggestCaptionsResponse {
  suggestions: CaptionSuggestionItem[];
  sanitized_prompt: string;
  pii_redactions: string[];
  provider_name: string;
  model_name: string;
  is_mock_provider: boolean;
  quota_remaining: number;
  daily_limit: number;
}

export interface MemeJobResponse {
  id: string;
  job_type: string;
  status: "draft" | "queued" | "generating" | "validating" | "ready" | "failed" | "cancelled";
  prompt: string;
  prompt_language: string;
  style_tone: string;
  attempt_count: number;
  provider_name?: string | null;
  model_version?: string | null;
  is_mock_provider: boolean;
  result_asset?: MemeAssetResponse | null;
  error_code?: string | null;
  error_message_safe?: string | null;
  quota_remaining?: number | null;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  completed_at?: string | null;
}

export async function fetchMemeTemplates(
  category?: string,
  options: RequestOptions = {}
): Promise<ApiResult<MemeTemplateListResponse>> {
  const qs = category ? `?category=${encodeURIComponent(category)}` : "";
  return apiRequest<MemeTemplateListResponse>(`/api/v1/memes/templates${qs}`, "GET", undefined, options);
}

export async function renderMemeTemplate(
  payload: {
    template_id_or_slug: string;
    captions: CaptionRegionInput[];
    language: string;
    alt_text?: string;
    output_format?: "PNG" | "WEBP";
  },
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<MemeAssetResponse>> {
  return apiRequest<MemeAssetResponse>("/api/v1/memes/render", "POST", payload, {
    ...options,
    csrfToken,
  });
}

export async function suggestMemeCaptions(
  payload: {
    prompt: string;
    tone: string;
    language: string;
    template_slug?: string;
  },
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<SuggestCaptionsResponse>> {
  return apiRequest<SuggestCaptionsResponse>("/api/v1/memes/captions", "POST", payload, {
    ...options,
    csrfToken,
  });
}

export async function createMemeJob(
  payload: {
    job_type?: "ai_image" | "template_render";
    prompt: string;
    style_tone: string;
    language: string;
    captions?: CaptionRegionInput[];
    alt_text?: string;
    idempotency_key?: string;
  },
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<MemeJobResponse>> {
  return apiRequest<MemeJobResponse>("/api/v1/memes/jobs", "POST", payload, {
    ...options,
    csrfToken,
  });
}

export async function fetchMemeJobStatus(
  jobId: string,
  options: RequestOptions = {}
): Promise<ApiResult<MemeJobResponse>> {
  return apiRequest<MemeJobResponse>(
    `/api/v1/memes/jobs/${encodeURIComponent(jobId)}`,
    "GET",
    undefined,
    options
  );
}

export async function cancelMemeJob(
  jobId: string,
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<MemeJobResponse>> {
  return apiRequest<MemeJobResponse>(
    `/api/v1/memes/jobs/${encodeURIComponent(jobId)}/cancel`,
    "POST",
    {},
    { ...options, csrfToken }
  );
}

export type ReportTargetType = "post" | "comment" | "profile" | "meme_asset";

export type ReportReasonCode =
  | "doxxing_pii"
  | "harassment"
  | "threat"
  | "impersonation"
  | "spam"
  | "hate_speech"
  | "confidential_ip"
  | "misleading_allegation"
  | "other";

export interface ReportResponse {
  id: string;
  target_type: ReportTargetType;
  target_id: string;
  reason_code: ReportReasonCode;
  details?: string | null;
  priority_score: number;
  status: string;
  protective_hold_triggered: boolean;
  created_at: string;
  updated_at: string;
}

export interface ModeratorTargetPreview {
  target_type: string;
  target_id: string;
  community_slug?: string | null;
  content_language: string;
  moderation_status: string;
  is_protective_hold: boolean;
  title?: string | null;
  body_excerpt: string;
  public_author?: PublicAuthorDisplay | null;
}

export interface ModerationQueueItemResponse {
  report_id: string;
  target_type: string;
  target_id: string;
  community_slug?: string | null;
  content_language: string;
  reason_code: string;
  details?: string | null;
  priority_score: number;
  status: string;
  distinct_reporter_count: number;
  allegation_notice: string;
  target_preview: ModeratorTargetPreview;
  created_at: string;
}

export interface CursorModerationQueueResponse {
  items: ModerationQueueItemResponse[];
  next_cursor?: string | null;
  has_more: boolean;
}

export interface ModerationActionResponse {
  id: string;
  actor_type: string;
  target_type: string;
  target_id: string;
  community_slug?: string | null;
  action_type: string;
  reason_code: string;
  public_explanation: string;
  previous_state?: string | null;
  new_state?: string | null;
  is_appealable: boolean;
  appeal_status?: string | null;
  created_at: string;
}

export interface AppealResponse {
  id: string;
  moderation_action_id: string;
  target_type: string;
  target_id: string;
  original_action_type: string;
  original_reason_code: string;
  public_explanation: string;
  appeal_statement: string;
  status: "pending" | "accepted" | "rejected";
  decision_reason_code?: string | null;
  review_decision_note?: string | null;
  can_viewer_decide: boolean;
  created_at: string;
  resolved_at?: string | null;
}

export interface BlockedAccountItem {
  handle: string;
  display_name: string;
  mode: "block" | "mute";
  created_at: string;
}

export interface AuditEventResponse {
  id: string;
  actor_user_id?: string | null;
  actor_role: string;
  event_category: string;
  action_name: string;
  target_type: string;
  target_id?: string | null;
  reason_code: string;
  redacted_metadata: Record<string, unknown>;
  correlation_id: string;
  created_at: string;
}

export interface CursorAuditEventListResponse {
  items: AuditEventResponse[];
  next_cursor?: string | null;
  has_more: boolean;
}

export async function submitReport(
  payload: {
    target_type: ReportTargetType;
    target_id: string;
    reason_code: ReportReasonCode;
    details?: string;
  },
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<ReportResponse>> {
  return apiRequest<ReportResponse>("/api/v1/reports", "POST", payload, {
    ...options,
    csrfToken,
  });
}

export async function fetchModerationQueue(
  params: {
    status?: string;
    reason_code?: string;
    target_type?: string;
    content_language?: string;
    community_slug?: string;
    high_severity_only?: boolean;
    cursor?: string;
  } = {},
  options: RequestOptions = {}
): Promise<ApiResult<CursorModerationQueueResponse>> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.reason_code) search.set("reason_code", params.reason_code);
  if (params.target_type) search.set("target_type", params.target_type);
  if (params.content_language) search.set("content_language", params.content_language);
  if (params.community_slug) search.set("community_slug", params.community_slug);
  if (params.high_severity_only) search.set("high_severity_only", "true");
  if (params.cursor) search.set("cursor", params.cursor);
  const qs = search.toString();
  return apiRequest<CursorModerationQueueResponse>(
    `/api/v1/moderation/queue${qs ? `?${qs}` : ""}`,
    "GET",
    undefined,
    options
  );
}

export async function executeModerationAction(
  payload: {
    target_type: string;
    target_id: string;
    action_type: string;
    reason_code: string;
    internal_note: string;
    public_explanation: string;
  },
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<ModerationActionResponse>> {
  return apiRequest<ModerationActionResponse>(
    "/api/v1/moderation/actions",
    "POST",
    payload,
    { ...options, csrfToken }
  );
}

export async function submitModerationAppeal(
  payload: {
    moderation_action_id: string;
    appeal_statement: string;
  },
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<AppealResponse>> {
  return apiRequest<AppealResponse>(
    "/api/v1/moderation/appeals",
    "POST",
    payload,
    { ...options, csrfToken }
  );
}

export async function decideModerationAppeal(
  appealId: string,
  payload: {
    decision: "accepted" | "rejected";
    decision_reason_code: string;
    review_decision_note: string;
  },
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<AppealResponse>> {
  return apiRequest<AppealResponse>(
    `/api/v1/moderation/appeals/${encodeURIComponent(appealId)}/decision`,
    "POST",
    payload,
    { ...options, csrfToken }
  );
}

export async function setUserBlockOrMute(
  handle: string,
  payload: { active: boolean; mode: "block" | "mute" },
  csrfToken: string,
  options: RequestOptions = {}
): Promise<ApiResult<{ handle: string; active: boolean; mode?: string | null }>> {
  return apiRequest<{ handle: string; active: boolean; mode?: string | null }>(
    `/api/v1/users/${encodeURIComponent(handle)}/block`,
    "PUT",
    payload,
    { ...options, csrfToken }
  );
}

export async function fetchModerationAuditEvents(
  params: {
    event_category?: string;
    action_name?: string;
    target_type?: string;
    reason_code?: string;
    cursor?: string;
  } = {},
  options: RequestOptions = {}
): Promise<ApiResult<CursorAuditEventListResponse>> {
  const search = new URLSearchParams();
  if (params.event_category) search.set("event_category", params.event_category);
  if (params.action_name) search.set("action_name", params.action_name);
  if (params.target_type) search.set("target_type", params.target_type);
  if (params.reason_code) search.set("reason_code", params.reason_code);
  if (params.cursor) search.set("cursor", params.cursor);
  const qs = search.toString();
  return apiRequest<CursorAuditEventListResponse>(
    `/api/v1/moderation/audit${qs ? `?${qs}` : ""}`,
    "GET",
    undefined,
    options
  );
}

export interface DerivedTranslationResponse {
  id: string;
  source_type: "post" | "comment";
  source_id: string;
  source_version_hash: string;
  source_language: string;
  source_language_label: string;
  detected_source_language?: string | null;
  is_source_language_uncertain: boolean;
  target_locale: string;
  target_locale_label: string;
  translated_title?: string | null;
  translated_body: string;
  direction: "ltr" | "rtl";
  provenance_label: string;
  provider_name: string;
  model_name: string;
  is_mock_provider: boolean;
  cache_hit: boolean;
  created_at: string;
}

export interface LanguageCapabilityItem {
  code: string;
  native_name: string;
  english_name: string;
  direction: "ltr" | "rtl";
  ui_locale_supported: boolean;
  content_posting_supported: boolean;
  on_demand_translation_target: boolean;
  meme_studio_font_shaping: string;
}

export interface LanguageCapabilitiesResponse {
  supported_ui_locales: string[];
  supported_translation_targets: string[];
  capabilities: LanguageCapabilityItem[];
}

export async function translatePost(
  postId: string,
  targetLocale: string,
  csrfToken?: string,
  options: RequestOptions = {}
): Promise<ApiResult<DerivedTranslationResponse>> {
  return apiRequest<DerivedTranslationResponse>(
    `/api/v1/posts/${encodeURIComponent(postId)}/translations`,
    "POST",
    { target_locale: targetLocale },
    { ...options, csrfToken }
  );
}

export async function translateComment(
  commentId: string,
  targetLocale: string,
  csrfToken?: string,
  options: RequestOptions = {}
): Promise<ApiResult<DerivedTranslationResponse>> {
  return apiRequest<DerivedTranslationResponse>(
    `/api/v1/comments/${encodeURIComponent(commentId)}/translations`,
    "POST",
    { target_locale: targetLocale },
    { ...options, csrfToken }
  );
}

export async function fetchLanguageCapabilities(
  options: RequestOptions = {}
): Promise<ApiResult<LanguageCapabilitiesResponse>> {
  return apiRequest<LanguageCapabilitiesResponse>(
    "/api/v1/languages/capabilities",
    "GET",
    undefined,
    options
  );
}

export interface PublicWorkplaceDetailSummary {
  experience_kind: "workplace_experience" | "resignation_story";
  experience_category: string;
  primary_resignation_reason?: string | null;
  secondary_resignation_reason?: string | null;
  experience_band?: string | null;
  industry_category?: string | null;
  transition_outcome?: string | null;
  lesson_learned?: string | null;
  is_self_reported: boolean;
}

export interface PrivateContributionResponse {
  id: string;
  aggregation_consent: boolean;
  industry_category?: string | null;
  role_family?: string | null;
  experience_band?: string | null;
  company_size_band?: string | null;
  broad_region?: string | null;
  work_arrangement?: string | null;
  overall_satisfaction?: number | null;
  workload_rating?: number | null;
  management_support?: number | null;
  work_life_balance?: number | null;
  career_growth?: number | null;
  workplace_flexibility?: number | null;
  compensation_satisfaction?: number | null;
  team_culture?: number | null;
  employee_autonomy?: number | null;
  resignation_reason?: string | null;
  is_self_reported: boolean;
  created_at: string;
  updated_at: string;
}

export interface AggregatedRatingMetricCard {
  metric_key: string;
  label: string;
  is_sensitive: boolean;
  minimum_threshold: number;
  insufficient_data: boolean;
  sample_size_band?: string | null;
  average_rating?: number | null;
  median_rating?: number | null;
  rating_distribution_pct?: Record<string, number> | null;
  status_message: string;
}

export interface ResignationReasonBucket {
  reason_code: string;
  percentage: number;
}

export interface AggregatedResignationBreakdown {
  minimum_threshold: number;
  insufficient_data: boolean;
  sample_size_band?: string | null;
  buckets: ResignationReasonBucket[];
  suppressed_other_percentage: number;
  status_message: string;
}

export interface WorkplaceInsightsMethodology {
  data_source_note: string;
  self_reported_disclaimer: string;
  general_min_cohort_threshold: number;
  sensitive_min_cohort_threshold: number;
  max_simultaneous_filters: number;
  free_text_excluded: boolean;
  employer_leaderboard_excluded: boolean;
  last_computed_at: string;
}

export interface WorkplaceInsightsResponse {
  selected_filters: Record<string, string>;
  cohort_eligible_band?: string | null;
  metrics: AggregatedRatingMetricCard[];
  resignation_reasons: AggregatedResignationBreakdown;
  methodology: WorkplaceInsightsMethodology;
}

export async function fetchWorkplaceExperiences(
  params: {
    category?: string;
    experience_band?: string;
    industry_category?: string;
    content_language?: string;
    sort?: "latest" | "popular";
    cursor?: string;
  } = {},
  options: RequestOptions = {}
): Promise<ApiResult<CursorPostListResponse>> {
  const search = new URLSearchParams();
  if (params.category) search.set("category", params.category);
  if (params.experience_band) search.set("experience_band", params.experience_band);
  if (params.industry_category) search.set("industry_category", params.industry_category);
  if (params.content_language) search.set("content_language", params.content_language);
  if (params.sort) search.set("sort", params.sort);
  if (params.cursor) search.set("cursor", params.cursor);
  const qs = search.toString();
  return apiRequest<CursorPostListResponse>(
    `/api/v1/workplace/experiences${qs ? `?${qs}` : ""}`,
    "GET",
    undefined,
    options
  );
}

export async function fetchResignationStories(
  params: {
    resignation_reason?: string;
    experience_band?: string;
    industry_category?: string;
    content_language?: string;
    sort?: "latest" | "popular";
    cursor?: string;
  } = {},
  options: RequestOptions = {}
): Promise<ApiResult<CursorPostListResponse>> {
  const search = new URLSearchParams();
  if (params.resignation_reason) search.set("resignation_reason", params.resignation_reason);
  if (params.experience_band) search.set("experience_band", params.experience_band);
  if (params.industry_category) search.set("industry_category", params.industry_category);
  if (params.content_language) search.set("content_language", params.content_language);
  if (params.sort) search.set("sort", params.sort);
  if (params.cursor) search.set("cursor", params.cursor);
  const qs = search.toString();
  return apiRequest<CursorPostListResponse>(
    `/api/v1/workplace/resignation-stories${qs ? `?${qs}` : ""}`,
    "GET",
    undefined,
    options
  );
}

export async function fetchWorkplaceInsights(
  params: {
    industry_category?: string;
    role_family?: string;
    experience_band?: string;
    company_size_band?: string;
    broad_region?: string;
    work_arrangement?: string;
  } = {},
  options: RequestOptions = {}
): Promise<ApiResult<WorkplaceInsightsResponse>> {
  const search = new URLSearchParams();
  if (params.industry_category) search.set("industry_category", params.industry_category);
  if (params.role_family) search.set("role_family", params.role_family);
  if (params.experience_band) search.set("experience_band", params.experience_band);
  if (params.company_size_band) search.set("company_size_band", params.company_size_band);
  if (params.broad_region) search.set("broad_region", params.broad_region);
  if (params.work_arrangement) search.set("work_arrangement", params.work_arrangement);
  const qs = search.toString();
  return apiRequest<WorkplaceInsightsResponse>(
    `/api/v1/workplace/insights${qs ? `?${qs}` : ""}`,
    "GET",
    undefined,
    options
  );
}
