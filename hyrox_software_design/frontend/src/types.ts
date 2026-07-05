export type SessionStatus = "idle" | "recording" | "paused" | "finished" | "finished_pending_report";

export interface SessionRecord {
  id: string;
  robot_session_id: string;
  device_id?: string | null;
  status: SessionStatus | string;
  started_at_ms?: number | null;
  ended_at_ms?: number | null;
  duration_s?: number | null;
  active_duration_s?: number | null;
  counts?: Record<string, number>;
}

export interface LiveEvent {
  type: string;
  timestamp_ms?: number;
  robot_timestamp_ms?: number | null;
  elapsed_ms?: number | null;
  robot_elapsed_ms?: number | null;
  action?: string;
  count?: number;
}

export interface LiveSnapshot {
  type: "live_snapshot";
  session_id: string;
  timestamp_ms: number;
  time_source?: string;
  status: SessionStatus | string;
  timer: {
    duration_s: number;
    active_duration_s: number;
  };
  current: {
    action: string;
    phase: string;
    posture: string;
    latest_score?: number | null;
  };
  counts: Record<string, number>;
  heart_rate: {
    bpm: number | null;
    zone?: number | null;
    percent_max?: number | null;
    status: string;
    device_name?: string;
    device_id?: string;
    timestamp_ms?: number;
  };
  robot: {
    device_id?: string | null;
    last_sample_age_ms?: number | null;
    target_confidence?: number | null;
    pose_quality: string;
    connection_status?: string;
    sample_count?: number;
    latest_sample_id?: number | null;
    elapsed_ms?: number;
    server_elapsed_ms?: number;
    robot_elapsed_ms?: number | null;
    received_at_ms?: number | null;
    robot_timestamp_ms?: number | null;
    angles?: Record<string, number>;
    visibility?: Record<string, boolean>;
  };
  notifications: {
    pushover_enabled: boolean | null;
    notify_reps: boolean;
  };
  events: LiveEvent[];
  warnings: string[];
}

export interface BleDevice {
  name: string;
  address: string;
  rssi?: number;
  service_uuids: string[];
  is_heart_rate_candidate: boolean;
}

export interface BleStatus {
  status: string;
  address?: string | null;
  name?: string | null;
  session_id?: string | null;
  message?: string;
  samples_received?: number;
  latest_bpm?: number | null;
  latest_sample_at_ms?: number | null;
  contact_detected?: boolean | null;
  single_device_only: boolean;
}

export interface NotificationSettings {
  pushover_enabled: boolean;
  notify_reps: boolean;
}
