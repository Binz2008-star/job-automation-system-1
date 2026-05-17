import {
  fetchChatHistory,
  fetchProfile,
  getApplications,
  getJobs,
} from '../api';
import { agentApi, ricoChatApi } from './client';
import type { Application, Job } from '@/types';

export interface CommandResponse {
  success: boolean;
  message: string;
  data?: unknown;
}

export interface TrajectoryForecast {
  nodes: Array<{
    id: string;
    title: string;
    description: string;
    probability: number;
    timeline: string;
    status: 'current' | 'upcoming' | 'completed';
  }>;
  currentPhase: string;
}

export interface OpportunitySignal {
  id: string;
  company: string;
  role: string;
  matchScore: number;
  momentum: 'high' | 'medium' | 'low';
  location: string;
  timestamp: string;
}

const EMPTY_TRAJECTORY: TrajectoryForecast = {
  nodes: [],
  currentPhase: 'live-backend-pending',
};

const EMPTY_SIGNALS: OpportunitySignal[] = [];

function deriveMomentum(job: Job): OpportunitySignal['momentum'] {
  const ageMs = job.posted_at ? Date.now() - new Date(job.posted_at).getTime() : Number.POSITIVE_INFINITY;
  const ageDays = Number.isFinite(ageMs) ? ageMs / (1000 * 60 * 60 * 24) : 999;
  if (job.score >= 85 && ageDays <= 7) return 'high';
  if (job.score >= 65 && ageDays <= 21) return 'medium';
  return 'low';
}

function applicationStatus(node: Application): TrajectoryForecast['nodes'][number]['status'] {
  switch (node.status) {
    case 'offer':
      return 'completed';
    case 'rejected':
      return 'completed';
    case 'interview':
    case 'applied':
    case 'opened':
    case 'saved':
      return 'current';
    default:
      return 'upcoming';
  }
}

function applicationProbability(status: Application['status']): number {
  switch (status) {
    case 'offer':
      return 0.9;
    case 'interview':
      return 0.72;
    case 'applied':
      return 0.55;
    case 'saved':
      return 0.42;
    case 'opened':
      return 0.38;
    case 'decision_made':
      return 0.8;
    default:
      return 0.2;
  }
}

export const orchestrationApi = {
  executeCommand: async (command: string): Promise<CommandResponse> => {
    const response = await agentApi.chat({ message: command });
    return {
      success: response.success,
      message: response.message,
      data: {
        actions: response.actions,
        ui: response.ui,
        tool_used: response.tool_used,
        execution_time_ms: response.execution_time_ms,
      },
    };
  },

  getTrajectory: async (): Promise<TrajectoryForecast> => {
    const [profile, applications, history] = await Promise.all([
      fetchProfile().catch(() => null),
      getApplications(undefined, 1, 5).catch(() => null),
      fetchChatHistory(6).catch(() => null),
    ]);

    if (!profile?.profile_exists) {
      return {
        nodes: [],
        currentPhase: 'profile-pending',
      };
    }

    const nodes: TrajectoryForecast['nodes'] = [];

    nodes.push({
      id: 'profile-current',
      title: profile.current_role || profile.name || profile.email || 'Profile established',
      description: profile.target_roles?.length
        ? `Targeting ${profile.target_roles.slice(0, 2).join(', ')}`
        : 'Profile is ready for richer trajectory analysis.',
      probability: Math.min(0.95, 0.45 + ((profile.completeness_score ?? 0) * 0.5)),
      timeline: 'Now',
      status: 'current',
    });

    if (profile.target_roles?.[0]) {
      nodes.push({
        id: 'trajectory-target',
        title: profile.target_roles[0],
        description: `Primary target role derived from your live Rico profile.`,
        probability: Math.min(0.88, 0.4 + ((profile.years_experience ?? 0) / 20)),
        timeline: applications?.applications.length ? 'Active pipeline' : 'Build pipeline',
        status: applications?.applications.length ? 'current' : 'upcoming',
      });
    }

    for (const application of applications?.applications.slice(0, 3) ?? []) {
      nodes.push({
        id: `application-${application.application_id}`,
        title: `${application.company} · ${application.title}`,
        description: `Pipeline status: ${application.status}${application.location ? ` · ${application.location}` : ''}`,
        probability: applicationProbability(application.status),
        timeline: application.applied_at
          ? new Date(application.applied_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
          : 'In progress',
        status: applicationStatus(application),
      });
    }

    if ((history?.messages.length ?? 0) > 0) {
      nodes.push({
        id: 'history-signal',
        title: 'Strategic memory active',
        description: `${history?.messages.length ?? 0} recent Rico interactions are informing the current command context.`,
        probability: 0.64,
        timeline: 'Recent',
        status: 'current',
      });
    }

    return {
      nodes,
      currentPhase: applications?.applications.length ? 'active-pipeline' : 'profile-ready',
    };
  },

  getSignals: async (): Promise<OpportunitySignal[]> => {
    const jobs = await getJobs(1, 6).catch(() => null);
    if (!jobs?.jobs.length) {
      return EMPTY_SIGNALS;
    }

    return jobs.jobs.map((job) => ({
      id: job.job_id,
      company: job.company,
      role: job.title,
      matchScore: job.score,
      momentum: deriveMomentum(job),
      location: job.location,
      timestamp: job.posted_at || '',
    }));
  },

  uploadCV: async (file: File): Promise<unknown> => {
    return ricoChatApi.uploadCV(file);
  },
};
