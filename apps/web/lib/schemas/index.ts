/**
 * Shared Rico API schemas.
 * These drive TypeScript inference across the app and runtime validation
 * where client callers parse responses at the boundary.
 */

import { z } from 'zod';

// ============================================================================
// Auth Schemas
// ============================================================================

export const LoginRequestSchema = z.object({
    email: z.string().email().min(1).max(256),
    password: z.string().min(1).max(128),
    public_user_id_to_merge: z.string().optional(),
});

export const RegisterRequestSchema = z.object({
    email: z.string().min(3).max(256),
    password: z.string().min(8).max(128),
    role: z.enum(['admin', 'user']).default('user'),
    public_user_id_to_merge: z.string().optional(),
});

export const LoginResponseSchema = z.object({
    message: z.string(),
    email: z.string(),
});

export const RegisterResponseSchema = z.object({
    email: z.string(),
    role: z.string(),
    created: z.boolean(),
});

// ============================================================================
// Job Schemas
// ============================================================================

export const JobActionRequestSchema = z.object({
    job: z.record(z.string(), z.any()),
});

export const JobActionResponseSchema = z.object({
    status: z.string(),
    message: z.string(),
    job_id: z.string().optional(),
});

export const JobListResponseSchema = z.object({
    jobs: z.array(z.record(z.string(), z.any())),
    total: z.number(),
    page: z.number(),
    limit: z.number(),
    pages: z.number(),
});

// ============================================================================
// Application Schemas
// ============================================================================

export const ApplicationCreateRequestSchema = z.object({
    job_id: z.string().min(1),
    title: z.string().min(1),
    company: z.string().min(1),
    location: z.string().default(''),
    url: z.string().default(''),
    status: z.string().default('opened'),
    source: z.string().default('manual'),
});

export const ManualApplicationCreateRequestSchema = z.object({
    title: z.string().min(1),
    company: z.string().min(1),
    location: z.string().default(''),
    url: z.string().default(''),
    status: z.string().default('applied'),
});

export const StatusUpdateRequestSchema = z.object({
    status: z.string().min(1),
    notes: z.string().optional(),
});

export const StatusUpdateResponseSchema = z.object({
    status: z.string(),
    job_id: z.string(),
    message: z.string(),
});

export const ApplicationListResponseSchema = z.object({
    applications: z.array(z.record(z.string(), z.any())),
    total: z.number(),
    page: z.number(),
    limit: z.number(),
    pages: z.number(),
});

// ============================================================================
// Pipeline Schemas
// ============================================================================

export const PipelineStatusResponseSchema = z.object({
    status: z.string(),
    started_at: z.string().optional(),
    finished_at: z.string().optional(),
    jobs_found: z.number().default(0),
    error: z.string().optional(),
    run_id: z.number().optional(),
});

export const PipelineTriggerResponseSchema = z.object({
    status: z.string(),
    message: z.string(),
});

// ============================================================================
// Stats Schemas
// ============================================================================

export const StatsResponseSchema = z.object({
    total_applied: z.number(),
    status_breakdown: z.record(z.string(), z.number()),
    interviews_scheduled: z.number(),
    rejections: z.number(),
    pending: z.number(),
    success_rate: z.number(),
});

// ============================================================================
// Settings Schemas
// ============================================================================

export const SettingsResponseSchema = z.object({
    include_keywords: z.array(z.string()),
    exclude_keywords: z.array(z.string()),
    min_score: z.number(),
    max_daily_applies: z.number(),
    telegram_chat_id: z.string(),
    score_threshold_apply: z.number(),
    score_threshold_watch: z.number(),
});

export const SettingsUpdateRequestSchema = z.object({
    include_keywords: z.array(z.string()).optional(),
    exclude_keywords: z.array(z.string()).optional(),
    min_score: z.number().optional(),
    max_daily_applies: z.number().optional(),
    telegram_chat_id: z.string().optional(),
    score_threshold_apply: z.number().optional(),
    score_threshold_watch: z.number().optional(),
});

// ============================================================================
// Agent Schemas
// ============================================================================

export const AgentUITypeSchema = z.enum([
    'job_list',
    'job_detail',
    'application_list',
    'stats',
    'pipeline_status',
    'text',
    'confirm',
    'error',
]);

export const ActionStyleSchema = z.enum(['primary', 'secondary', 'danger']);

export const AgentActionSchema = z.object({
    action_id: z.string().default(() => Math.random().toString(36).substring(2, 10)),
    type: z.string(),
    label: z.string(),
    style: ActionStyleSchema.default('secondary'),
    job_id: z.string().optional(),
    job: z.record(z.string(), z.any()).optional(),
    metadata: z.record(z.string(), z.any()).default({}),
});

export const AgentUIComponentSchema = z.object({
    type: AgentUITypeSchema,
    title: z.string().optional(),
    data: z.record(z.string(), z.any()).default({}),
});

export const AgentChatRequestSchema = z.object({
    message: z.string().min(1).max(1000),
    action: AgentActionSchema.optional(),
});

export const AgentUIResponseSchema = z.object({
    message: z.string(),
    ui: AgentUIComponentSchema.optional(),
    actions: z.array(AgentActionSchema).default(() => []),
    tool_used: z.string().optional(),
    execution_time_ms: z.number().default(0),
    success: z.boolean().default(true),
});

// ============================================================================
// Rico Chat Schemas
// ============================================================================

export const RicoChatRequestSchema = z.object({
    message: z.string().max(4096),
});

export const RicoPublicChatRequestSchema = z.object({
    message: z.string().max(2048),
    session_id: z.string().min(8).max(64).optional(),
    email: z.string().email().optional(),
});

export const RicoFeedbackRequestSchema = z.object({
    job_id: z.string().min(1).max(100),
    feedback_type: z.enum(['positive', 'negative', 'neutral']),
    rating: z.number().int().min(1).max(5),
    comment: z.string().max(500).optional(),
});

export const MeResponseSchema = z.object({
    email: z.string().nullable(),
    role: z.string(),
    authenticated: z.boolean(),
    guest: z.boolean().optional(),
});

export const JobMatchSchema = z.object({
    title: z.string(),
    company: z.string(),
    location: z.string().optional(),
    score: z.number().optional(),
    why: z.string().optional(),
    actions: z.array(z.string()).optional(),
    confidence: z.enum(['high', 'medium', 'low']).optional(),
    match_reasons: z.array(z.string()).optional(),
    match_concerns: z.array(z.string()).optional(),
    missing_facts: z.array(z.string()).optional(),
    recommended_action: z.string().optional(),
}).passthrough();

export const RicoOptionSchema = z.object({
    action: z.string(),
    label: z.string(),
    message: z.string().optional(),
    role: z.string().optional(),
}).passthrough();

export const NextActionSchema = z.object({
    action: z.string(),
    label: z.string(),
    message: z.string().optional(),
    role: z.string().optional(),
}).passthrough();

export const RicoChatResponseSchema = z.object({
    response: z.string().optional(),
    reply: z.string().optional(),
    message: z.string().optional(),
    content: z.string().optional(),
    answer: z.string().optional(),
    text: z.string().optional(),
    data: z.object({
        response: z.string().optional(),
        reply: z.string().optional(),
        message: z.string().optional(),
        content: z.string().optional(),
        text: z.string().optional(),
    }).passthrough().optional(),
    type: z.string().optional(),
    matches: z.array(JobMatchSchema).optional(),
    options: z.array(RicoOptionSchema).optional(),
    next_action: z.string().optional(),
    response_source: z.string().optional(),
    role: z.string().optional(),
    reasons: z.array(z.string()).optional(),
    next_actions: z.array(NextActionSchema).optional(),
    success: z.boolean().optional(),
    debug_id: z.string().optional(),
    error: z.string().optional(),
    error_ref: z.string().optional(),
    provider: z.string().optional(),
    model: z.string().optional(),
    profile_context_present: z.boolean().optional(),
}).passthrough();

export const RicoProfileResponseSchema = z.object({
    profile_exists: z.boolean(),
    email: z.string().optional(),
    user_id: z.string().optional(),
    name: z.string().nullable().optional(),
    phone: z.string().nullable().optional(),
    telegram_username: z.string().nullable().optional(),
    target_roles: z.array(z.string()).optional(),
    preferred_cities: z.array(z.string()).optional(),
    salary_expectation_aed: z.number().nullable().optional(),
    minimum_salary_aed: z.number().nullable().optional(),
    skills: z.array(z.string()).optional(),
    industries: z.array(z.string()).optional(),
    visa_status: z.string().nullable().optional(),
    notice_period: z.string().nullable().optional(),
    years_experience: z.number().nullable().optional(),
    current_role: z.string().nullable().optional(),
    current_company: z.string().nullable().optional(),
    linkedin_url: z.string().nullable().optional(),
    completeness_score: z.number().nullable().optional(),
    settings: z.record(z.string(), z.unknown()).optional(),
}).passthrough();

export const SavedSearchSchema = z.object({
    id: z.union([z.string(), z.number()]).transform(String),
    query: z.string(),
    filters: z.record(z.string(), z.unknown()),
    created_at: z.string(),
}).passthrough();

export const SavedSearchesResponseSchema = z.object({
    searches: z.array(SavedSearchSchema),
    total: z.number(),
});

export const RicoChatHistoryMessageSchema = z.object({
    role: z.string(),
    content: z.string(),
    timestamp: z.string().nullable().optional(),
}).passthrough();

export const RicoChatHistoryResponseSchema = z.object({
    messages: z.array(RicoChatHistoryMessageSchema),
    total: z.number(),
    has_more: z.boolean(),
}).passthrough();

export const ParsedCVSchema = z.object({
    text: z.string(),
    emails: z.array(z.string()),
    phones: z.array(z.string()),
    skills: z.array(z.string()),
    certifications: z.array(z.string()),
    languages: z.array(z.string()),
    years_experience_hint: z.number().nullable().optional(),
    years_experience: z.number().nullable().optional(),
    extraction_quality: z.string().optional(),
    extracted_chars: z.number().optional(),
}).passthrough();

export const ProfilePreviewSchema = z.object({
    name: z.string().nullable(),
    email: z.string().nullable(),
    phone: z.string().nullable(),
    current_role: z.string().nullable(),
    experience_years: z.number().nullable(),
    target_roles: z.array(z.string()),
    skills_detected: z.array(z.string()),
    existing_skills: z.array(z.string()),
    skills: z.array(z.string()),
    certifications: z.array(z.string()),
    languages: z.array(z.string()),
}).passthrough();

export const UploadCVResponseSchema = z.object({
    ok: z.boolean(),
    status: z.string(),
    document_type: z.string().optional(),
    extraction_quality: z.string().optional(),
    extracted_chars: z.number().optional(),
    filename: z.string().optional(),
    preview: ProfilePreviewSchema.optional(),
    parsed: ParsedCVSchema.optional(),
    message: z.string().optional(),
    user_id: z.string().optional(),
}).passthrough();

export const ConfirmCVProfileResponseSchema = z.object({
    ok: z.boolean(),
    status: z.string(),
    message: z.string(),
    profile: z.record(z.string(), z.unknown()),
}).passthrough();

export const ProfileUpdateResponseSchema = z.object({
    status: z.string(),
    updated_fields: z.array(z.string()),
}).passthrough();

// ============================================================================
// Memory Schemas (for persistent memory system)
// ============================================================================

export const LongitudinalMemorySchema = z.object({
    user_id: z.string(),
    timestamp: z.string(),
    event_type: z.enum([
        'job_viewed',
        'job_applied',
        'job_saved',
        'job_skipped',
        'company_blocked',
        'recruiter_contact',
        'interview_scheduled',
        'offer_received',
        'offer_accepted',
        'offer_rejected',
        'compensation_update',
        'preference_update',
    ]),
    job_id: z.string().optional(),
    company: z.string().optional(),
    recruiter: z.string().optional(),
    compensation: z.object({
        salary: z.number().optional(),
        equity: z.string().optional(),
        bonus: z.number().optional(),
        benefits: z.array(z.string()).optional(),
    }).optional(),
    preferences: z.object({
        locations: z.array(z.string()).optional(),
        roles: z.array(z.string()).optional(),
        industries: z.array(z.string()).optional(),
        remote: z.boolean().optional(),
        min_salary: z.number().optional(),
    }).optional(),
    metadata: z.record(z.string(), z.any()).optional(),
});

export const TrajectoryHistorySchema = z.object({
    user_id: z.string(),
    timestamp: z.string(),
    trajectory_state: z.object({
        current_role: z.string(),
        target_roles: z.array(z.string()),
        career_stage: z.enum(['early', 'mid', 'senior', 'executive']),
        momentum_score: z.number(),
        convergence_probability: z.number(),
        strategic_positioning: z.object({
            market_fit: z.number(),
            skill_alignment: z.number(),
            opportunity_density: z.number(),
        }),
    }),
    nodes: z.array(z.object({
        id: z.string(),
        type: z.enum(['opportunity', 'milestone', 'decision', 'outcome']),
        title: z.string(),
        probability: z.number(),
        timing: z.object({
            optimal: z.string().optional(),
            window_start: z.string().optional(),
            window_end: z.string().optional(),
            decay_rate: z.number().optional(),
        }),
    })),
});

export const RecruiterInteractionSchema = z.object({
    user_id: z.string(),
    recruiter_id: z.string(),
    recruiter_name: z.string(),
    company: z.string(),
    timestamp: z.string(),
    interaction_type: z.enum([
        'initial_contact',
        'screening_call',
        'technical_interview',
        'behavioral_interview',
        'offer_negotiation',
        'follow_up',
    ]),
    outcome: z.enum([
        'pending',
        'positive',
        'negative',
        'offer',
        'rejected',
    ]),
    response_time_hours: z.number().optional(),
    communication_style: z.enum(['formal', 'casual', 'direct', 'relationship-focused']).optional(),
    metadata: z.record(z.string(), z.any()).optional(),
});

export const CompensationTargetSchema = z.object({
    user_id: z.string(),
    timestamp: z.string(),
    target: z.object({
        base_salary: z.number(),
        equity: z.string().optional(),
        bonus: z.number().optional(),
        benefits_value: z.number().optional(),
        total_compensation: z.number(),
    }),
    current: z.object({
        base_salary: z.number(),
        equity: z.string().optional(),
        bonus: z.number().optional(),
        benefits_value: z.number().optional(),
        total_compensation: z.number(),
    }),
    trajectory: z.object({
        target_date: z.string(),
        confidence: z.number(),
        required_moves: z.array(z.string()),
    }),
});

export const StrategicPreferenceSchema = z.object({
    user_id: z.string(),
    timestamp: z.string(),
    preferences: z.object({
        career_velocity: z.enum(['conservative', 'moderate', 'aggressive']),
        risk_tolerance: z.enum(['low', 'medium', 'high']),
        geographic_flexibility: z.enum(['none', 'regional', 'national', 'global']),
        industry_focus: z.array(z.string()),
        role_evolution: z.enum(['specialist', 'generalist', 'leader']),
        work_life_balance: z.number().min(0).max(10),
        learning_priority: z.number().min(0).max(10),
        compensation_priority: z.number().min(0).max(10),
        title_progression: z.array(z.string()),
    }),
});

export const OpportunityWeightingSchema = z.object({
    user_id: z.string(),
    opportunity_id: z.string(),
    timestamp: z.string(),
    weights: z.object({
        strategic_fit: z.number().min(0).max(1),
        compensation_alignment: z.number().min(0).max(1),
        growth_potential: z.number().min(0).max(1),
        market_timing: z.number().min(0).max(1),
        recruiter_quality: z.number().min(0).max(1),
        cultural_alignment: z.number().min(0).max(1),
    }),
    momentum_score: z.number(),
    decay_probability: z.number(),
    saturation_window: z.object({
        start: z.string().optional(),
        end: z.string().optional(),
        intensity: z.number().min(0).max(1),
    }),
});

// ============================================================================
// Type Exports
// ============================================================================

export type LoginRequest = z.infer<typeof LoginRequestSchema>;
export type RegisterRequest = z.infer<typeof RegisterRequestSchema>;
export type LoginResponse = z.infer<typeof LoginResponseSchema>;
export type RegisterResponse = z.infer<typeof RegisterResponseSchema>;

export type JobActionRequest = z.infer<typeof JobActionRequestSchema>;
export type JobActionResponse = z.infer<typeof JobActionResponseSchema>;
export type JobListResponse = z.infer<typeof JobListResponseSchema>;

export type ApplicationCreateRequest = z.infer<typeof ApplicationCreateRequestSchema>;
export type ManualApplicationCreateRequest = z.infer<typeof ManualApplicationCreateRequestSchema>;
export type StatusUpdateRequest = z.infer<typeof StatusUpdateRequestSchema>;
export type StatusUpdateResponse = z.infer<typeof StatusUpdateResponseSchema>;
export type ApplicationListResponse = z.infer<typeof ApplicationListResponseSchema>;

export type PipelineStatusResponse = z.infer<typeof PipelineStatusResponseSchema>;
export type PipelineTriggerResponse = z.infer<typeof PipelineTriggerResponseSchema>;

export type StatsResponse = z.infer<typeof StatsResponseSchema>;

export type SettingsResponse = z.infer<typeof SettingsResponseSchema>;
export type SettingsUpdateRequest = z.infer<typeof SettingsUpdateRequestSchema>;

export type AgentAction = z.infer<typeof AgentActionSchema>;
export type AgentUIComponent = z.infer<typeof AgentUIComponentSchema>;
export type AgentChatRequest = z.infer<typeof AgentChatRequestSchema>;
export type AgentUIResponse = z.infer<typeof AgentUIResponseSchema>;

export type RicoChatRequest = z.infer<typeof RicoChatRequestSchema>;
export type RicoPublicChatRequest = z.infer<typeof RicoPublicChatRequestSchema>;
export type RicoFeedbackRequest = z.infer<typeof RicoFeedbackRequestSchema>;
export type MeResponse = z.infer<typeof MeResponseSchema>;
export type RicoChatResponse = z.infer<typeof RicoChatResponseSchema>;
export type RicoProfileResponse = z.infer<typeof RicoProfileResponseSchema>;
export type SavedSearch = z.infer<typeof SavedSearchSchema>;
export type SavedSearchesResponse = z.infer<typeof SavedSearchesResponseSchema>;
export type RicoChatHistoryResponse = z.infer<typeof RicoChatHistoryResponseSchema>;
export type ParsedCV = z.infer<typeof ParsedCVSchema>;
export type ProfilePreview = z.infer<typeof ProfilePreviewSchema>;
export type UploadCVResponse = z.infer<typeof UploadCVResponseSchema>;
export type ConfirmCVProfileResponse = z.infer<typeof ConfirmCVProfileResponseSchema>;
export type ProfileUpdateResponse = z.infer<typeof ProfileUpdateResponseSchema>;

export type LongitudinalMemory = z.infer<typeof LongitudinalMemorySchema>;
export type TrajectoryHistory = z.infer<typeof TrajectoryHistorySchema>;
export type RecruiterInteraction = z.infer<typeof RecruiterInteractionSchema>;
export type CompensationTarget = z.infer<typeof CompensationTargetSchema>;
export type StrategicPreference = z.infer<typeof StrategicPreferenceSchema>;
export type OpportunityWeighting = z.infer<typeof OpportunityWeightingSchema>;
