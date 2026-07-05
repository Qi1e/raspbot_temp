"""Workout program state and frontend-facing progress summaries."""

import time
from dataclasses import dataclass, field

from .state import WorkoutStatus


@dataclass(frozen=True)
class WorkoutStation:
    """One count-based station in a workout program."""

    name: str
    action: str
    target_count: int


@dataclass(frozen=True)
class WorkoutEvent:
    """Event emitted when workout progress changes materially."""

    type: str
    station: str
    action: str
    count: int
    target_count: int
    elapsed_ms: int


@dataclass(frozen=True)
class WorkoutProgram:
    """Count-based workout program definition."""

    name: str
    stations: tuple = field(default_factory=tuple)


def build_hyrox_program(args):
    """Build the default HYROX-style program from CLI arguments."""
    return WorkoutProgram(
        name=getattr(args, 'workout_program', 'HYROX'),
        stations=(
            WorkoutStation('Squats', 'squat', max(0, int(getattr(args, 'workout_squat_target', 20)))),
            WorkoutStation('Lunges', 'lunge', max(0, int(getattr(args, 'workout_lunge_target', 20)))),
            WorkoutStation('Burpees', 'burpee', max(0, int(getattr(args, 'workout_burpee_target', 10)))),
        ),
    )


class WorkoutSession:
    """Mutable workout session that consumes action counts."""

    def __init__(self, program, session_id=''):
        self.program = program
        self.session_id = session_id or time.strftime('%Y%m%d_%H%M%S')
        self.started_at = time.time()
        self.station_index = 0
        self.completed = False
        self.last_counts = {}
        self.events = []

    def update(self, actions, now=None):
        """Advance station progress from the current action statuses."""
        now = time.time() if now is None else now
        if not self.program.stations:
            return self.status(now)

        for name, status in actions.items():
            previous = self.last_counts.get(name, 0)
            self.last_counts[name] = status.count
            if status.count > previous:
                self.events.append(
                    WorkoutEvent(
                        type='rep',
                        station=self.current_station().name if not self.completed else '',
                        action=name,
                        count=status.count,
                        target_count=self.current_station().target_count if not self.completed else 0,
                        elapsed_ms=self.elapsed_ms(now),
                    )
                )

        while not self.completed:
            station = self.current_station()
            count = actions.get(station.action).count if station.action in actions else 0
            if station.target_count <= 0 or count < station.target_count:
                break
            self.events.append(
                WorkoutEvent(
                    type='station_complete',
                    station=station.name,
                    action=station.action,
                    count=count,
                    target_count=station.target_count,
                    elapsed_ms=self.elapsed_ms(now),
                )
            )
            self.station_index += 1
            if self.station_index >= len(self.program.stations):
                self.completed = True
                self.events.append(
                    WorkoutEvent(
                        type='workout_complete',
                        station=station.name,
                        action=station.action,
                        count=count,
                        target_count=station.target_count,
                        elapsed_ms=self.elapsed_ms(now),
                    )
                )
                break

        return self.status(now)

    def current_station(self):
        """Return the active station, clamping after completion."""
        if not self.program.stations:
            return WorkoutStation('', '', 0)
        index = min(self.station_index, len(self.program.stations) - 1)
        return self.program.stations[index]

    def elapsed_ms(self, now):
        return int((now - self.started_at) * 1000)

    def status(self, now=None):
        """Return immutable workout status for state snapshots."""
        now = time.time() if now is None else now
        station = self.current_station()
        current_count = self.last_counts.get(station.action, 0)
        target = station.target_count
        action_progress = 1.0 if target <= 0 else min(1.0, current_count / float(target))
        if not self.program.stations:
            overall_progress = 0.0
        else:
            overall_progress = min(
                1.0,
                (self.station_index + (0.0 if self.completed else action_progress)) / float(len(self.program.stations)),
            )
        return WorkoutStatus(
            session_id=self.session_id,
            program_name=self.program.name,
            current_station='' if self.completed else station.name,
            current_action='' if self.completed else station.action,
            station_index=min(self.station_index + 1, len(self.program.stations)),
            total_stations=len(self.program.stations),
            target_count=0 if self.completed else target,
            current_count=current_count,
            elapsed_ms=self.elapsed_ms(now),
            action_progress=action_progress,
            overall_progress=overall_progress,
            completed=self.completed,
            events=tuple(event.__dict__ for event in self.events[-8:]),
        )
