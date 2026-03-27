import { useCallback, useState } from 'react';

export function useFireworks() {
    const [isActive, setIsActive] = useState(false);

    const launch = useCallback((duration: number = 5000) => {
        setIsActive(true);
        window.setTimeout(() => setIsActive(false), duration);
    }, []);

    const stop = useCallback(() => setIsActive(false), []);

    return { isActive, launch, stop };
}
