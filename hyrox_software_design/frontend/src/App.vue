<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  Activity,
  Bell,
  BellOff,
  Bluetooth,
  Camera,
  CheckCircle2,
  Eye,
  EyeOff,
  HeartPulse,
  PlugZap,
  RefreshCw,
  Search,
  Timer,
  Wifi,
  XCircle
} from "lucide-vue-next";
import {
  connectHeartRateDevice,
  disconnectHeartRateDevice,
  finishSession,
  getHeartRateStatus,
  getLatestSession,
  getLiveSnapshot,
  getNotificationSettings,
  getSessions,
  scanHeartRateDevices,
  updateNotificationSettings
} from "./api";
import type { BleDevice, BleStatus, LiveEvent, LiveSnapshot, NotificationSettings, SessionRecord } from "./types";

const DEFAULT_CAMERA_PREVIEW_URL = "http://192.168.1.11:8080/";

const latestSession = ref<SessionRecord | null>(null);
const sessions = ref<SessionRecord[]>([]);
const snapshot = ref<LiveSnapshot | null>(null);
const bleDevices = ref<BleDevice[]>([]);
const bleStatus = ref<BleStatus | null>(null);
const notificationSettings = ref<NotificationSettings | null>(null);
const selectedSessionId = ref("");
const cameraPreviewEnabled = ref(localStorage.getItem("hyrox.camera.enabled") === "true");
const cameraPreviewUrl = ref(localStorage.getItem("hyrox.camera.url") || DEFAULT_CAMERA_PREVIEW_URL);
const loading = ref({
  refresh: false,
  scan: false,
  connect: "",
  disconnect: false,
  notification: false,
  finish: false
});
const errorMessage = ref("");
const wsState = ref("closed");
let socket: WebSocket | null = null;
let pollingTimer: number | undefined;

const activeSessionId = computed(() => selectedSessionId.value || latestSession.value?.id || snapshot.value?.session_id || "");
const canFinishSession = computed(() => {
  const status = snapshot.value?.status || latestSession.value?.status || "";
  return Boolean(activeSessionId.value) && !["finished", "finished_pending_report"].includes(status);
});

const durationText = computed(() => formatDuration(snapshot.value?.timer.duration_s ?? latestSession.value?.duration_s ?? 0));
const activeDurationText = computed(() => formatDuration(snapshot.value?.timer.active_duration_s ?? 0));
const currentActionText = computed(() => actionLabel(snapshot.value?.current.action || "none"));
const currentPhaseText = computed(() => phaseLabel(snapshot.value?.current.phase || "unknown"));
const heartRateText = computed(() => {
  const bpm = snapshot.value?.heart_rate.bpm ?? bleStatus.value?.latest_bpm;
  return bpm ? `${bpm}` : "--";
});
const heartRateStatusText = computed(() => {
  if (snapshot.value?.heart_rate.bpm) return statusLabel(snapshot.value.heart_rate.status);
  if (bleStatus.value?.latest_bpm) return `最近样本 ${bleStatus.value.samples_received ?? 0} 条`;
  return statusLabel(bleStatus.value?.status || snapshot.value?.heart_rate.status || "missing");
});
const poseConfidenceText = computed(() => {
  const confidence = snapshot.value?.robot.target_confidence;
  return typeof confidence === "number" ? `${Math.round(confidence * 100)}%` : "--";
});
const robotConnectionText = computed(() => {
  const age = snapshot.value?.robot.last_sample_age_ms;
  if (snapshot.value?.status === "finished_pending_report") return "已结束";
  if (typeof age !== "number") return statusLabel(snapshot.value?.robot.connection_status || "offline");
  if (age < 3000) return "实时";
  if (age < 10000) return "延迟";
  return "离线";
});
const robotDataCountText = computed(() => `${snapshot.value?.robot.sample_count ?? 0}`);
const robotElapsedText = computed(() => {
  const elapsedMs = snapshot.value?.robot.server_elapsed_ms ?? snapshot.value?.robot.elapsed_ms ?? 0;
  return formatDuration(elapsedMs / 1000);
});
const robotRawElapsedText = computed(() => {
  const elapsedMs = snapshot.value?.robot.robot_elapsed_ms;
  return typeof elapsedMs === "number" ? formatDuration(elapsedMs / 1000) : "--";
});
const jointRows = computed(() => {
  const angles = snapshot.value?.robot.angles || {};
  const keys = [
    "left_knee",
    "right_knee",
    "left_hip",
    "right_hip",
    "left_elbow",
    "right_elbow",
    "left_shoulder",
    "right_shoulder"
  ];
  return keys.map((key) => ({
    key,
    label: jointLabel(key),
    value: typeof angles[key] === "number" ? `${angles[key].toFixed(1)}°` : "--"
  }));
});
const sortedEvents = computed(() => [...(snapshot.value?.events || [])].reverse());

function formatDuration(seconds: number) {
  const total = Math.max(0, Math.round(seconds || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours) return `${hours}小时 ${minutes}分 ${secs}秒`;
  if (minutes) return `${minutes}分 ${secs}秒`;
  return `${secs}秒`;
}

function actionLabel(action: string) {
  const map: Record<string, string> = {
    squat: "深蹲",
    lunge: "箭步蹲",
    burpee: "波比跳",
    none: "待识别"
  };
  return map[action] || "待识别";
}

function jointLabel(joint: string) {
  const map: Record<string, string> = {
    left_knee: "左膝",
    right_knee: "右膝",
    left_hip: "左髋",
    right_hip: "右髋",
    left_elbow: "左肘",
    right_elbow: "右肘",
    left_shoulder: "左肩",
    right_shoulder: "右肩"
  };
  return map[joint] || joint;
}

function phaseLabel(phase: string) {
  const map: Record<string, string> = {
    up: "站起",
    down: "下蹲",
    pushup_down: "俯卧撑下降",
    pushup_up: "俯卧撑推起",
    stand_recovery: "起身",
    broad_jump: "跳远",
    unknown: "未知"
  };
  return map[phase] || phase;
}

function statusLabel(status?: string) {
  const map: Record<string, string> = {
    idle: "空闲",
    recording: "记录中",
    paused: "暂停",
    finished: "已结束",
    finished_pending_report: "待生成报告",
    connected: "已连接",
    connecting: "连接中",
    listening: "监听中",
    disconnected: "已断开",
    error: "异常",
    live: "实时",
    missing: "缺失"
  };
  return map[status || ""] || status || "未知";
}

function eventText(event: LiveEvent) {
  if (event.type === "rep_event") return `${actionLabel(event.action || "")} +1，第 ${event.count ?? "--"} 次`;
  if (event.type === "session_start") return "已开始运动";
  if (event.type === "session_end") return "训练结束";
  return event.type;
}

function eventTime(event: LiveEvent) {
  if (!event.timestamp_ms) return "--";
  return new Date(event.timestamp_ms).toLocaleTimeString("zh-CN", { hour12: false });
}

async function refreshAll() {
  loading.value.refresh = true;
  errorMessage.value = "";
  try {
    const [latest, sessionList, settings, hrStatus] = await Promise.all([
      getLatestSession(),
      getSessions(),
      getNotificationSettings(),
      getHeartRateStatus()
    ]);
    latestSession.value = latest.session;
    if (latest.live_snapshot) snapshot.value = latest.live_snapshot;
    sessions.value = sessionList.items;
    notificationSettings.value = settings;
    bleStatus.value = hrStatus;
    if (!selectedSessionId.value && latest.session?.id) selectedSessionId.value = latest.session.id;
    if (activeSessionId.value) {
      await refreshSnapshot(activeSessionId.value);
      connectLiveSocket(activeSessionId.value);
    }
  } catch (error) {
    setError(error);
  } finally {
    loading.value.refresh = false;
  }
}

async function refreshSnapshot(sessionId: string) {
  try {
    snapshot.value = await getLiveSnapshot(sessionId);
  } catch (error) {
    setError(error);
  }
}

async function scanDevices() {
  loading.value.scan = true;
  errorMessage.value = "";
  try {
    const result = await scanHeartRateDevices(10);
    bleDevices.value = result.items;
  } catch (error) {
    setError(error);
  } finally {
    loading.value.scan = false;
  }
}

async function connectDevice(device: BleDevice) {
  loading.value.connect = device.address;
  errorMessage.value = "";
  try {
    bleStatus.value = await connectHeartRateDevice({
      address: device.address,
      session_id: activeSessionId.value || undefined
    });
  } catch (error) {
    setError(error);
  } finally {
    loading.value.connect = "";
  }
}

async function connectByName() {
  loading.value.connect = "name";
  errorMessage.value = "";
  try {
    bleStatus.value = await connectHeartRateDevice({
      name: "vivo WATCH",
      session_id: activeSessionId.value || undefined
    });
  } catch (error) {
    setError(error);
  } finally {
    loading.value.connect = "";
  }
}

async function disconnectDevice() {
  loading.value.disconnect = true;
  errorMessage.value = "";
  try {
    bleStatus.value = await disconnectHeartRateDevice();
  } catch (error) {
    setError(error);
  } finally {
    loading.value.disconnect = false;
  }
}

async function toggleRepNotification() {
  if (!notificationSettings.value) return;
  loading.value.notification = true;
  errorMessage.value = "";
  try {
    notificationSettings.value = await updateNotificationSettings({
      notify_reps: !notificationSettings.value.notify_reps
    });
    if (snapshot.value) {
      snapshot.value.notifications.notify_reps = notificationSettings.value.notify_reps;
    }
  } catch (error) {
    setError(error);
  } finally {
    loading.value.notification = false;
  }
}

async function finishActiveSession() {
  if (!activeSessionId.value || !canFinishSession.value) return;
  loading.value.finish = true;
  errorMessage.value = "";
  try {
    const result = await finishSession(activeSessionId.value);
    latestSession.value = result.session;
    snapshot.value = result.live_snapshot;
    sessions.value = (await getSessions()).items;
  } catch (error) {
    setError(error);
  } finally {
    loading.value.finish = false;
  }
}

function selectSession(sessionId: string) {
  selectedSessionId.value = sessionId;
  refreshSnapshot(sessionId);
  connectLiveSocket(sessionId);
}

function saveCameraSettings() {
  localStorage.setItem("hyrox.camera.enabled", String(cameraPreviewEnabled.value));
  localStorage.setItem("hyrox.camera.url", cameraPreviewUrl.value);
}

function toggleCameraPreview() {
  cameraPreviewEnabled.value = !cameraPreviewEnabled.value;
  saveCameraSettings();
}

function connectLiveSocket(sessionId: string) {
  if (!sessionId) return;
  if (socket) socket.close();
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${protocol}://${window.location.host}/ws/v1/live/${encodeURIComponent(sessionId)}`);
  wsState.value = "connecting";
  socket.onopen = () => {
    wsState.value = "connected";
  };
  socket.onmessage = (event) => {
    snapshot.value = JSON.parse(event.data) as LiveSnapshot;
  };
  socket.onerror = () => {
    wsState.value = "error";
  };
  socket.onclose = () => {
    wsState.value = "closed";
  };
}

function setError(error: unknown) {
  errorMessage.value = error instanceof Error ? error.message : String(error);
}

onMounted(() => {
  refreshAll();
  pollingTimer = window.setInterval(() => {
    if (activeSessionId.value) refreshSnapshot(activeSessionId.value);
    getHeartRateStatus().then((status) => (bleStatus.value = status)).catch(() => undefined);
  }, 5000);
});

onBeforeUnmount(() => {
  if (socket) socket.close();
  if (pollingTimer) window.clearInterval(pollingTimer);
});
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">HYROX Training Console</p>
        <h1>实时训练控制台</h1>
      </div>
      <div class="topbar-actions">
        <span class="status-pill" :class="wsState">
          <Wifi :size="16" />
          {{ statusLabel(wsState) }}
        </span>
        <button class="icon-button" title="刷新" :disabled="loading.refresh" @click="refreshAll">
          <RefreshCw :size="18" :class="{ spin: loading.refresh }" />
        </button>
      </div>
    </header>

    <section v-if="errorMessage" class="alert">
      <XCircle :size="18" />
      <span>{{ errorMessage }}</span>
    </section>

    <section class="overview-grid">
      <div class="metric-panel primary">
        <div class="metric-icon"><Timer :size="22" /></div>
        <span>本次运动时间</span>
        <strong>{{ durationText }}</strong>
        <small>有效 {{ activeDurationText }}</small>
      </div>
      <div class="metric-panel">
        <div class="metric-icon"><Activity :size="22" /></div>
        <span>当前动作</span>
        <strong>{{ currentActionText }}</strong>
        <small>{{ currentPhaseText }}</small>
      </div>
      <div class="metric-panel">
        <div class="metric-icon"><HeartPulse :size="22" /></div>
        <span>心率</span>
        <strong>{{ heartRateText }}</strong>
        <small>{{ heartRateStatusText }}</small>
      </div>
      <div class="metric-panel">
        <div class="metric-icon"><CheckCircle2 :size="22" /></div>
        <span>姿态质量</span>
        <strong>{{ statusLabel(snapshot?.robot.pose_quality) }}</strong>
        <small>目标置信度 {{ poseConfidenceText }}</small>
      </div>
    </section>

    <section class="workspace-grid">
      <section class="panel session-panel">
        <div class="panel-header">
          <div>
            <h2>训练状态</h2>
            <p>{{ activeSessionId || "暂无 session" }}</p>
          </div>
          <div class="button-row">
            <span class="status-pill recording">{{ statusLabel(snapshot?.status || latestSession?.status) }}</span>
            <button class="tool-button" :disabled="!canFinishSession || loading.finish" @click="finishActiveSession">
              <XCircle :size="16" />
              结束记录
            </button>
          </div>
        </div>

        <div class="counts-grid">
          <div class="count-tile">
            <span>深蹲</span>
            <strong>{{ snapshot?.counts.squat ?? 0 }}</strong>
          </div>
          <div class="count-tile">
            <span>箭步蹲</span>
            <strong>{{ snapshot?.counts.lunge ?? 0 }}</strong>
          </div>
          <div class="count-tile">
            <span>波比跳</span>
            <strong>{{ snapshot?.counts.burpee ?? 0 }}</strong>
          </div>
        </div>

        <div class="session-list">
          <button
            v-for="session in sessions.slice(0, 6)"
            :key="session.id"
            :class="{ active: session.id === activeSessionId }"
            @click="selectSession(session.id)"
          >
            <span>{{ session.id }}</span>
            <small>{{ statusLabel(session.status) }}</small>
          </button>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>小车数据</h2>
            <p>{{ snapshot?.robot.device_id || "未连接" }} · {{ robotConnectionText }}</p>
          </div>
          <span class="status-pill" :class="{ connected: robotConnectionText === '实时', closed: robotConnectionText === '离线' }">
            <Wifi :size="16" />
            {{ robotConnectionText }}
          </span>
        </div>

        <div class="robot-stats">
          <div>
            <span>运动数据个数</span>
            <strong>{{ robotDataCountText }}</strong>
          </div>
          <div>
            <span>最新样本</span>
            <strong>{{ snapshot?.robot.latest_sample_id ?? "--" }}</strong>
          </div>
          <div>
            <span>电脑运动时间</span>
            <strong>{{ robotElapsedText }}</strong>
          </div>
          <div>
            <span>小车原始耗时</span>
            <strong>{{ robotRawElapsedText }}</strong>
          </div>
        </div>

        <div class="joint-grid">
          <div v-for="joint in jointRows" :key="joint.key" class="joint-cell">
            <span>{{ joint.label }}</span>
            <strong>{{ joint.value }}</strong>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>心率设备</h2>
            <p>
              单设备模式 · {{ statusLabel(bleStatus?.status) }}
              <template v-if="bleStatus?.samples_received !== undefined">
                · 样本 {{ bleStatus.samples_received }}
              </template>
            </p>
          </div>
          <div class="button-row">
            <button class="tool-button" :disabled="loading.scan" @click="scanDevices">
              <Search :size="16" />
              扫描
            </button>
            <button class="tool-button" :disabled="loading.connect === 'name'" @click="connectByName">
              <Bluetooth :size="16" />
              连接
            </button>
            <button class="icon-button" title="断开心率设备" :disabled="loading.disconnect" @click="disconnectDevice">
              <PlugZap :size="18" />
            </button>
          </div>
        </div>

        <div class="device-list">
          <button
            v-for="device in bleDevices"
            :key="device.address"
            :class="{ candidate: device.is_heart_rate_candidate }"
            :disabled="loading.connect === device.address"
            @click="connectDevice(device)"
          >
            <span>
              <Bluetooth :size="16" />
              {{ device.name }}
            </span>
            <small>{{ device.address }} · RSSI {{ device.rssi ?? "--" }}</small>
          </button>
          <div v-if="!bleDevices.length" class="empty-state">暂无扫描结果</div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>通知</h2>
            <p>Pushover · {{ notificationSettings?.pushover_enabled ? "可用" : "关闭" }}</p>
          </div>
          <button
            class="toggle-button"
            :class="{ on: notificationSettings?.notify_reps }"
            :disabled="loading.notification"
            @click="toggleRepNotification"
          >
            <Bell v-if="notificationSettings?.notify_reps" :size="16" />
            <BellOff v-else :size="16" />
            动作通知
          </button>
        </div>
        <div class="notification-state">
          <span>训练开始</span>
          <strong>开启</strong>
          <span>动作完成</span>
          <strong>{{ notificationSettings?.notify_reps ? "开启" : "关闭" }}</strong>
          <span>训练结束</span>
          <strong>开启</strong>
        </div>
      </section>

      <section class="panel camera-panel">
        <div class="panel-header">
          <div>
            <h2>摄像头预览</h2>
            <p>{{ cameraPreviewUrl || "未设置地址" }}</p>
          </div>
          <button class="toggle-button" :class="{ on: cameraPreviewEnabled }" @click="toggleCameraPreview">
            <Eye v-if="cameraPreviewEnabled" :size="16" />
            <EyeOff v-else :size="16" />
            预览
          </button>
        </div>
        <div class="camera-controls">
          <Camera :size="18" />
          <input
            v-model="cameraPreviewUrl"
            type="url"
            placeholder="http://192.168.1.11:8080/"
            @change="saveCameraSettings"
            @blur="saveCameraSettings"
          />
        </div>
        <div class="camera-frame">
          <iframe
            v-if="cameraPreviewEnabled && cameraPreviewUrl"
            :src="cameraPreviewUrl"
            title="Raspbot camera preview"
            loading="lazy"
          />
          <div v-else class="empty-state">预览关闭</div>
        </div>
      </section>

      <section class="panel event-panel">
        <div class="panel-header">
          <div>
            <h2>最近事件</h2>
            <p>{{ sortedEvents.length }} 条</p>
          </div>
        </div>
        <ol class="event-list">
          <li v-for="event in sortedEvents" :key="`${event.type}-${event.timestamp_ms}-${event.count}`">
            <time>{{ eventTime(event) }}</time>
            <span>{{ eventText(event) }}</span>
          </li>
        </ol>
        <div v-if="!sortedEvents.length" class="empty-state">暂无事件</div>
      </section>
    </section>
  </main>
</template>
