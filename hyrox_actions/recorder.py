"""JSONL recording for HYROX action and joint-angle samples."""

import json
import time
from pathlib import Path


class JsonlRecorder:
    """Append action snapshots to a JSONL file."""

    def __init__(self, path='', interval=0.2, min_confidence=0.55):
        self.path = Path(path).expanduser() if path else None
        self.interval = max(0.0, float(interval))
        self.min_confidence = float(min_confidence)
        self.last_recorded_at = 0.0

    @property
    def enabled(self):
        """Return whether recording is enabled."""
        return self.path is not None

    def record(self, posture, features, actions):
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

        payload = {
            'timestamp': now,
            'posture': posture,
            'active_action': active_action,
            'target': {
                'area': features.target.area,
                'width': features.target.width,
                'height': features.target.height,
                'center_x': features.target.center_x,
                'center_y': features.target.center_y,
                'confidence': features.target.confidence,
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

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a', encoding='utf-8') as output:
            output.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + '\n')
        self.last_recorded_at = now
