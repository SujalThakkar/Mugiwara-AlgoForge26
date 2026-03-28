/**
 * Shared Goal type used across components.
 */
export interface Goal {
  id: string;
  name: string;
  icon: string;
  target: number;
  current: number;
  deadline: string;
  priority: string;
  color: string;
  milestones?: {
    amount: number;
    reached: boolean;
    date: string | null;
  }[];
  goal_type?: string;
  progress_percentage?: number;
  remaining?: number;
  on_track?: boolean;
  eta_days?: number | null;
  chain_status?: string;
  badge_tx_hash?: string | null;
  wallet_address?: string | null;
}
