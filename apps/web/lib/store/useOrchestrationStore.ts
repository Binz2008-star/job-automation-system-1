import { create } from 'zustand';
import { orchestrationApi } from '@/lib/api/orchestration';

interface TrajectoryNode {
  id: string;
  title: string;
  description: string;
  probability: number;
  timeline: string;
  status: 'current' | 'upcoming' | 'completed';
}

interface OpportunitySignal {
  id: string;
  company: string;
  role: string;
  matchScore: number;
  momentum: 'high' | 'medium' | 'low';
  location: string;
  timestamp: string;
}

interface OrchestrationState {
  trajectory: TrajectoryNode[];
  signals: OpportunitySignal[];
  commandHistory: string[];
  isProcessing: boolean;
  currentCommand: string;
  setTrajectory: (nodes: TrajectoryNode[]) => void;
  setSignals: (signals: OpportunitySignal[]) => void;
  addTrajectoryNode: (node: TrajectoryNode) => void;
  addSignal: (signal: OpportunitySignal) => void;
  executeCommand: (command: string) => Promise<void>;
  setProcessing: (processing: boolean) => void;
}

export const useOrchestrationStore = create<OrchestrationState>((set, get) => ({
  trajectory: [],
  signals: [],
  commandHistory: [],
  isProcessing: false,
  currentCommand: '',
  setTrajectory: (nodes) => {
    set({ trajectory: nodes });
  },
  setSignals: (signals) => {
    set({ signals });
  },
  addTrajectoryNode: (node) => {
    set((state) => ({ trajectory: [...state.trajectory, node] }));
  },
  addSignal: (signal) => {
    set((state) => ({ signals: [...state.signals, signal] }));
  },
  executeCommand: async (command: string) => {
    set({ currentCommand: command, isProcessing: true });
    try {
      await orchestrationApi.executeCommand(command);
      set((state) => ({ 
        commandHistory: [...state.commandHistory, command],
        isProcessing: false,
        currentCommand: ''
      }));
    } catch (error) {
      set({ isProcessing: false, currentCommand: '' });
      throw error;
    }
  },
  setProcessing: (processing) => {
    set({ isProcessing: processing });
  },
}));
