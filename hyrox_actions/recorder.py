"""JSONL/NDJSON recording for HYROX action and joint-angle samples."""

import json
import queue
import threading
import time
import uuid
from pathlib import Path
from urllib import request
from urllib.parse import urlparse


_STOP = object()


KEYPOINT_INDICES = {
    'left_shoulder': 11,
    'right_shoulder': 12,
    'left_elbow': 13,
    'right_elbow': 14,
    'left_wrist': 15,
    'right_wrist': 16,
    'left_hip': 23,
    'right_hip': 24,
    'left_knee': 25,
    'right_knee': 26,
    'left_ankle': 27,
    'right_ankle': 28,
}


class JsonlRecorder:
    """Append action snapshots locally and optionally upload NDJSON batches."""

    def __init__(
        self,
        path='',
        interval=0.2,
        min_confidence=0.55,
        url='',
        session_id='',
        device_id='raspbot',
        upload_batch_size=10,
        upload_interval=1.0,
        upload_queue_size=300,
        include_keypoints=False,
    ):
        self.path = Path(path).expanduser() if path else None
        self.interval = max(0.0, float(interval))
        self.min_confidence = float(min_confidence)
        self.url = str(url or '').strip()
        self.session_id = session_id or time.strftime('%Y%m%d_%H%M%S')
        self.device_id = device_id or 'raspbot'
        self.upload_batch_size = max(1, int(upload_batch_size))
        self.upload_interval = max(0.1, float(upload_interval))
        self.include_keypoints = bool(include_keypoints)
        self.last_recorded_at = 0.0
        self.started_at = time.time()
        self.sample_id = 0
        self.last_counts = {}
        self.last_actions = {}
        self.uploaded_batches = 0
        self.failed_uploads = 0
        self.last_upload_error = ''
        self._remote_queue = None
        self._remote_thread = None
        self._remote_enabled = self._is_supported_url(self.url)
        if self.url and not self._remote_enabled:
            print(f'Record upload disabled: unsupported record URL scheme: {self.url}')
        if self._remote_enabled:
            self._remote_queue = queue.Queue(maxsize=max(1, int(upload_queue_size)))
            self._remote_thread = threading.Thread(target=self._upload_worker, daemon=True)
            self._remote_thread.start()

    @property
    def enabled(self):
        """Return whether recording is enabled."""
        return self.path is not None or self._remote_enabled

    @property
    def remote_enabled(self):
        """Return whether remote upload is enabled."""
        return self._remote_enabled

    @staticmethod
    def _is_supported_url(url):
        """Return whether url can be uploaded with stdlib HTTP."""
        if not url:
            return False
        return urlparse(url).scheme in ('http', 'https')

    def start(self, config=None):
        """Emit a session_start event."""
        if not self.enabled:
            return
        self._write_payload(
            {
                'type': 'session_start',
                'schema_version': '1.0',
                'session_id': self.session_id,
                'device_id': self.device_id,
                'timestamp': self.started_at,
                'config': config or {},
            }
        )

    def record(self, posture, features, actions, landmarks=None):
        """Record one sample if configured and interval/confidence gates pass."""
        if not self.enabled:
            return

        now = time.time()
        if now - self.last_recorded_at < self.interval:
            return
        if features.target.confidence < self.min_confidence:
            return

        active_action = 'none'
        for name in ('burpee', 'lunge', 'squat'):
            status = actions.get(name)
            if not status:
                continue
            if name == 'burpee' and status.active:
                active_action = name
                break
            if name != 'burpee' and (status.active or status.stage == 'down'):
                active_action = name
                break

        self.sample_id += 1
        payload = {
            'type': 'sample',
            'schema_version': '1.0',
            'session_id': self.session_id,
            'device_id': self.device_id,
            'sample_id': self.sample_id,
            'timestamp': now,
            'elapsed_ms': int((now - self.started_at) * 1000),
            'posture': posture,
            'active_action': active_action,
            'target': {
                'detected': features.target.detected,
                'area': features.target.area,
                'width': features.target.width,
                'height': features.target.height,
                'center_x': features.target.center_x,
                'center_y': features.target.center_y,
                'confidence': features.target.confidence,
            },
            'visibility': {
                'full_body': features.full_body,
                'arms_visible': features.arms_visible,
                'legs_visible': features.legs_visible,
            },
            'angles': features.key_angles(),
            'features': features.key_features(),
            'actions': {
                name: {
                    'count': status.count,
                    'stage': status.stage,
                    'active': status.active,
                    'confidence': status.confidence,
                    'details': status.details,
                }
                for name, status in actions.items()
            },
        }
        if self.include_keypoints and landmarks is not None:
            payload['keypoints'] = self._keypoints(landmarks)

        self._write_payload(payload)
        self._emit_rep_events(actions, now)
        self.last_recorded_at = now

    def close(self):
        """Emit session_end and stop the upload worker."""
        if self.enabled:
            self._write_payload(
                {
                    'type': 'session_end',
                    'schema_version': '1.0',
                    'session_id': self.session_id,
                    'device_id': self.device_id,
                    'timestamp': time.time(),
                    'elapsed_ms': int((time.time() - self.started_at) * 1000),
                    'counts': self.last_counts,
                }
            )
        if self._remote_queue is not None:
            try:
                self._remote_queue.put_nowait(_STOP)
            except queue.Full:
                pass
        if self._remote_thread is not None:
            self._remote_thread.join(timeout=2.0)

    def _emit_rep_events(self, actions, now):
        """Emit one event whenever a counter increases."""
        for name, status in actions.items():
            previous = self.last_counts.get(name, 0)
            self.last_counts[name] = status.count
            self.last_actions[name] = status.stage
            if status.count <= previous:
                continue
            self._write_payload(
                {
                    'type': 'rep_event',
                    'schema_version': '1.0',
                    'session_id': self.session_id,
                    'device_id': self.device_id,
                    'timestamp': now,
                    'elapsed_ms': int((now - self.started_at) * 1000),
                    'action': name,
                    'count': status.count,
                    'stage': status.stage,
                    'details': status.details,
                }
            )

    def _write_payload(self, payload):
        """Write one event locally and enqueue it for remote upload."""
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('a', encoding='utf-8') as output:
                output.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + '\n')
        if self._remote_queue is not None:
            try:
                self._remote_queue.put_nowait(payload)
            except queue.Full:
                self.failed_uploads += 1

    def _upload_worker(self):
        """Upload queued events as NDJSON batches without blocking inference."""
        pending = []
        last_flush = time.time()
        while True:
            timeout = max(0.1, self.upload_interval - (time.time() - last_flush))
            try:
                item = self._remote_queue.get(timeout=timeout)
            except queue.Empty:
                item = None

            if item is _STOP:
                break
            if item is not None:
                pending.append(item)

            should_flush = (
                pending
                and (
                    len(pending) >= self.upload_batch_size
                    or time.time() - last_flush >= self.upload_interval
                )
            )
            if should_flush:
                self._post_batch(pending)
                pending = []
                last_flush = time.time()

        while True:
            try:
                item = self._remote_queue.get_nowait()
            except queue.Empty:
                break
            if item is not _STOP:
                pending.append(item)
        if pending:
            self._post_batch(pending)

    def _post_batch(self, payloads):
        """POST one NDJSON batch to the configured receiver."""
        body = ''.join(
            json.dumps(payload, ensure_ascii=True, sort_keys=True) + '\n'
            for payload in payloads
        ).encode('utf-8')
        req = request.Request(
            self.url,
            data=body,
            headers={
                'Content-Type': 'application/x-ndjson',
                'X-Raspbot-Session-Id': self.session_id,
                'X-Raspbot-Device-Id': self.device_id,
            },
            method='POST',
        )
        try:
            with request.urlopen(req, timeout=2.0) as response:
                response.read()
            self.uploaded_batches += 1
            self.last_upload_error = ''
        except Exception as exc:  # noqa: BLE001 - keep recorder non-fatal on Pi.
            self.failed_uploads += len(payloads)
            self.last_upload_error = str(exc)

    @staticmethod
    def _keypoints(landmarks):
        """Return selected normalized keypoints as [x, y, visibility]."""
        result = {}
        for name, index in KEYPOINT_INDICES.items():
            if index >= len(landmarks):
                continue
            lm = landmarks[index]
            result[name] = [round(lm.x, 4), round(lm.y, 4), round(lm.visibility, 4)]
        return result
