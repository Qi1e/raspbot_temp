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

export interface SessionReport {
  type: "session_report";
  session_id: string;
  generated_at_ms: number;
  session: {
    id: string;
    status: string;
    device_id?: string | null;
    started_at_ms?: number | null;
    ended_at_ms?: number | null;
    duration_s: number;
    time_source: string;
  };
  summary: {
    duration_s: number;
    total_reps: number;
    completion_score: number;
    completion_level: string;
    calories_kcal: number;
    avg_bpm?: number | null;
    max_bpm?: number | null;
    min_bpm?: number | null;
    heart_rate_sample_count: number;
    robot_sample_count: number;
    action_event_count: number;
  };
  heart_rate: {
    table: HeartRateReportRow[];
    stats: {
      sample_count: number;
      avg_bpm?: number | null;
      max_bpm?: number | null;
      min_bpm?: number | null;
    };
    time_axis: {
      started_at_ms?: number | null;
      description: string;
    };
  };
  movement: {
    counts: MovementCountRow[];
    raw_counts: Record<string, number>;
    completion: CompletionAnalysis;
  };
  calories: {
    kcal: number;
    duration_min: number;
    estimated_met: number;
    adult_reference: {
      weight_kg: number;
      max_heart_rate_bpm: number;
    };
    method: string;
    confidence: string;
  };
  notes: string[];
}

export interface HeartRateReportRow {
  t_ms?: number | null;
  time: string;
  timestamp_ms?: number | null;
  bpm?: number | null;
  zone?: string | null;
  nearest_action?: {
    action?: string | null;
    label: string;
    count?: number | null;
    delta_ms: number;
    text: string;
  } | null;
}

export interface MovementCountRow {
  action: string;
  label: string;
  count: number;
  target: number;
  completion_percent: number;
}

export interface CompletionAnalysis {
  score: number;
  level: string;
  total_reps: number;
  target_reps: number;
  volume_score: number;
  balance_score: number;
  pose_quality_score: number;
  pose_quality: {
    score: number;
    avg_target_confidence?: number | null;
    full_body_visible_rate?: number | null;
    sample_count: number;
  };
  by_action: MovementCountRow[];
  reference: {
    name: string;
    targets: Record<string, number>;
    note: string;
  };
}
