import { orchestrationApi } from '@/lib/api/orchestration';
import { useOrchestrationStore } from '@/lib/store/useOrchestrationStore';
import { useCallback, useEffect, useState } from 'react';

export function useOrchestration() {
    const { trajectory, signals, setTrajectory, setSignals, isProcessing } = useOrchestrationStore();
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchTrajectory = useCallback(async () => {
        try {
            const data = await orchestrationApi.getTrajectory();
            setTrajectory(data.nodes);
            setError(null);
        } catch (err) {
            setError('Failed to fetch trajectory data');
            console.error(err);
        }
    }, [setTrajectory]);

    const fetchSignals = useCallback(async () => {
        try {
            const data = await orchestrationApi.getSignals();
            setSignals(data);
            setError(null);
        } catch (err) {
            setError('Failed to fetch signals');
            console.error(err);
        }
    }, [setSignals]);

    const executeCommand = useCallback(async (command: string) => {
        setError(null);
        try {
            const response = await orchestrationApi.executeCommand(command);
            return response;
        } catch (err) {
            setError('Failed to execute command');
            console.error(err);
            throw err;
        }
    }, []);

    useEffect(() => {
        let cancelled = false;

        const load = async () => {
            try {
                await Promise.all([fetchTrajectory(), fetchSignals()]);
            } finally {
                if (!cancelled) {
                    setIsLoading(false);
                }
            }
        };

        void load();

        return () => {
            cancelled = true;
        };
    }, [fetchSignals, fetchTrajectory]);

    const refetchTrajectory = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
            await fetchTrajectory();
        } finally {
            setIsLoading(false);
        }
    }, [fetchTrajectory]);

    const refetchSignals = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
            await fetchSignals();
        } finally {
            setIsLoading(false);
        }
    }, [fetchSignals]);

    return {
        trajectory,
        signals,
        isLoading,
        isProcessing,
        error,
        executeCommand,
        refetchTrajectory,
        refetchSignals,
    };
}
