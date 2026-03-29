// src/lib/api/client.ts
import axios from 'axios';

// API Configuration
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'https://babylike-overtimorously-stacey.ngrok-free.dev/api';

// Axios instance
export const apiClient = axios.create({
    baseURL: API_BASE_URL,
    timeout: 60000,
    headers: {
        'Content-Type': 'application/json',
        'ngrok-skip-browser-warning': '1',  // suppress ngrok interstitial page
    },
});

// Smart fetch wrapper
export async function smartFetch<T>(
    endpoint: string,
    options?: {
        method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
        data?: any;
    }
): Promise<T> {
    
    // REAL MODE - Hit actual API
    console.log(`🌐 [REAL] Fetching ${endpoint} from API`);

    try {
        const response = await apiClient.request<T>({
            url: endpoint,
            method: options?.method || 'GET',
            data: options?.data,
        });

        return response.data;
    } catch (error) {
        console.error(`❌ API Error on ${endpoint}:`, error);
        throw error;
    }
}
