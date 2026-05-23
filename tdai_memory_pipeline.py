"""
tdai_memory_pipeline.py — Python port of TencentDB-Agent-Memory's MemoryPipelineManager.

L0→L1→L2→L3 memory extraction pipeline scheduler, ported from TypeScript to Python
for integration with qclaw's existing memory infrastructure.

## Layered Architecture

- **L0 (capture)**: Raw conversation messages are buffered per-session.
- **L1 (atomic facts)**: When conversation count reaches threshold or idle timeout fires,
  buffered messages are batch-processed to extract structured facts.
- **L2 (scene blocks)**: Downward-only timer aggregates L1 facts into scene narratives.
- **L3 (persona)**: Global dedup protects persona generation from concurrent triggers.

## Key Design Features

- **Warm-up mode**: New sessions trigger L1 at 1→2→4→...→N conversations
- **Downward-only L2 timer**: L2 can only fire earlier, never later (prevents starvation)
- **Session GC**: Cold sessions are evicted from memory to prevent unbounded growth
- **Checkpoint recovery**: All state persisted to JSON checkpoint, recoverable on restart
- **Atomic writes**: tmp+rename pattern prevents corruption on crash

## Integration with qclaw

- Hooks into evolver.py's record_agent_fact() for L1 extraction
- File-based storage: JSONL for L0/L1 facts, Markdown for L2 scenes/L3 persona
- Uses threading.Timer for idle timeout scheduling

Source: Tencent/TencentDB-Agent-Memory (GitHub, 2k stars)
"""

import json
import os
import time
import threading
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable, Dict, List, Any
from collections import deque

logger = logging.getLogger("tdai.pipeline")

# ============================
# Data Types
# ============================

@dataclass
class PipelineConfig:
    """Pipeline scheduling configuration (all time values in seconds)."""
    # L1: conversation threshold
    every_n_conversations: int = 5
    enable_warmup: bool = True
    l1_idle_timeout_seconds: int = 600  # 10 min

    # L2: scene extraction
    l2_delay_after_l1_seconds: int = 90
    l2_min_interval_seconds: int = 900   # 15 min
    l2_max_interval_seconds: int = 3600  # 1 hour
    l2_session_active_window_hours: int = 24

    # Retry
    l1_retry_delay_seconds: int = 30
    l1_max_retries: int = 5

    # GC
    session_gc_inactive_multiplier: int = 3
    session_gc_every_n_notifications: int = 50

    # L3
    persona_trigger_every_n_memories: int = 50

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PipelineSessionState:
    """Per-session pipeline state (persisted to checkpoint)."""
    conversation_count: int = 0
    last_extraction_time: str = ""
    last_extraction_updated_time: str = ""
    last_active_time: float = 0.0
    l2_pending_l1_count: int = 0
    warmup_threshold: int = 1  # 0 = graduated
    l2_last_extraction_time: str = ""


@dataclass
class Checkpoint:
    """Full checkpoint with global counters and per-session states."""
    # Global
    last_captured_timestamp: float = 0.0
    total_processed: int = 0
    last_persona_at: int = 0
    last_persona_time: str = ""
    request_persona_update: bool = False
    persona_update_reason: str = ""
    memories_since_last_persona: int = 0
    scenes_processed: int = 0
    l0_conversations_count: int = 0
    total_memories_extracted: int = 0

    # Per-session
    pipeline_states: Dict[str, PipelineSessionState] = field(default_factory=dict)


@dataclass
class CapturedMessage:
    """A single captured message ready for L1 processing."""
    role: str  # "user" | "assistant" | "tool"
    content: str
    timestamp: str  # ISO format


# ============================
# CheckpointManager — Atomic JSON persistence
# ============================

class CheckpointManager:
    """Manages atomic read/write of pipeline checkpoint to JSON file.

    Uses tmp+rename pattern to prevent corruption on crash.
    Thread-safe via a per-file lock.
    """

    def __init__(self, data_dir: str):
        os.makedirs(os.path.join(data_dir, ".metadata"), exist_ok=True)
        self.file_path = os.path.join(data_dir, ".metadata", "pipeline_checkpoint.json")
        self._lock = threading.Lock()

    def read(self) -> Checkpoint:
        """Read checkpoint from disk (returns defaults if file missing)."""
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return Checkpoint()

        cp = Checkpoint()
        # Global counters
        for k in Checkpoint.__dataclass_fields__:
            if k != "pipeline_states" and k in raw:
                setattr(cp, k, raw[k])

        # Per-session pipeline states
        if "pipeline_states" in raw:
            for session_key, state_dict in raw["pipeline_states"].items():
                cp.pipeline_states[session_key] = PipelineSessionState(**{
                    k: v for k, v in state_dict.items()
                    if k in PipelineSessionState.__dataclass_fields__
                })
        return cp

    def write(self, cp: Checkpoint) -> None:
        """Atomic write: tmp file then rename."""
        with self._lock:
            dirname = os.path.dirname(self.file_path)
            os.makedirs(dirname, exist_ok=True)
            tmp_path = f"{self.file_path}.tmp.{os.getpid()}"
            data = asdict(cp)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.file_path)

    def merge_pipeline_states(self, states: Dict[str, PipelineSessionState]) -> None:
        """Merge pipeline states into checkpoint (used by pipeline persister)."""
        cp = self.read()
        for key, p_state in states.items():
            cp.pipeline_states[key] = p_state
        self.write(cp)

    def get_all_pipeline_states(self) -> Dict[str, PipelineSessionState]:
        """Get all pipeline session states."""
        return self.read().pipeline_states

    def mark_persona_generated(self, total_processed: int) -> None:
        cp = self.read()
        cp.last_persona_at = total_processed
        cp.last_persona_time = time.strftime("%Y-%m-%dT%H:%M:%S")
        cp.memories_since_last_persona = 0
        cp.request_persona_update = False
        cp.persona_update_reason = ""
        self.write(cp)

    def increment_memories_extracted(self, count: int) -> None:
        cp = self.read()
        cp.total_memories_extracted += count
        cp.memories_since_last_persona += count
        self.write(cp)


# ============================
# SerialQueue — Single-consumer async queue
# ============================

class SerialQueue:
    """A simple serial task queue ensuring one-at-a-time execution."""

    def __init__(self, name: str = ""):
        self.name = name
        self._queue: deque = deque()
        self._lock = threading.Lock()
        self._running = False
        self._idle_event = threading.Event()
        self._idle_event.set()  # starts idle

    @property
    def size(self) -> int:
        return len(self._queue)

    @property
    def pending(self) -> bool:
        return self._running or len(self._queue) > 0

    @property
    def idle(self) -> bool:
        return not self.pending

    def add(self, task: Callable[[], None]) -> None:
        """Add a task to the queue and start processing."""
        with self._lock:
            self._queue.append(task)
            self._idle_event.clear()
        self._process_next()

    def on_idle(self, timeout: float = 30.0) -> bool:
        """Wait until the queue becomes idle."""
        return self._idle_event.wait(timeout)

    def _process_next(self) -> None:
        with self._lock:
            if self._running:
                return
            if not self._queue:
                self._idle_event.set()
                return
            task = self._queue.popleft()
            self._running = True

        try:
            task()
        except Exception:
            logger.exception(f"[SerialQueue:{self.name}] Task failed")
        finally:
            with self._lock:
                self._running = False
            self._process_next()


# ============================
# ManagedTimer — Resettable / downward-only timer
# ============================

class ManagedTimer:
    """A resettable timer that supports both reset-on-new-event (L1 idle)
    and downward-only (L2 schedule) semantics."""

    def __init__(self, name: str, is_destroyed: Callable[[], bool]):
        self.name = name
        self._is_destroyed = is_destroyed
        self._timer: Optional[threading.Timer] = None
        self._callback: Optional[Callable[[], None]] = None
        self.scheduled_time: float = 0.0  # epoch seconds when timer will fire

    @property
    def pending(self) -> bool:
        return self._timer is not None and self._timer.is_alive()

    def schedule(self, delay_seconds: float, callback: Callable[[], None]) -> None:
        """Schedule (or reschedule) a timer. Replaces any existing timer."""
        self.cancel()
        if self._is_destroyed():
            return
        self._callback = callback
        self.scheduled_time = time.time() + delay_seconds
        self._timer = threading.Timer(delay_seconds, self._on_fire)
        self._timer.daemon = True
        self._timer.start()

    def schedule_at(self, fire_at_epoch: float, callback: Callable[[], None]) -> None:
        """Schedule a timer to fire at a specific epoch time."""
        delay = max(0, fire_at_epoch - time.time())
        self.schedule(delay, callback)

    def try_advance_to(self, desired_time: float, callback: Callable[[], None]) -> bool:
        """Advance timer to desired_time only if it's earlier than current schedule."""
        if self.pending and self.scheduled_time <= desired_time:
            return False  # current schedule is already earlier
        self.schedule_at(desired_time, callback)
        return True

    def cancel(self) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None
        self._callback = None
        self.scheduled_time = 0.0

    def flush(self) -> None:
        """Cancel timer and fire callback immediately if pending."""
        cb = self._callback
        self.cancel()
        if cb:
            cb()

    def _on_fire(self) -> None:
        if self._is_destroyed():
            return
        self._timer = None
        self.scheduled_time = 0.0
        cb = self._callback
        self._callback = None
        if cb:
            try:
                cb()
            except Exception:
                logger.exception(f"[ManagedTimer:{self.name}] Callback failed")


# ============================
# SessionFilter — Exclude internal/benchmark sessions
# ============================

class SessionFilter:
    """Filter out internal/benchmark sessions from pipeline processing."""

    def __init__(self, exclude_patterns: List[str] = None):
        import fnmatch
        self._patterns = exclude_patterns or []
        self._fnmatch = fnmatch

    def should_skip(self, session_key: str) -> bool:
        for pattern in self._patterns:
            if self._fnmatch.fnmatch(session_key, pattern):
                return True
        return False


# ============================
# MemoryPipelineManager — Core scheduler
# ============================

class MemoryPipelineManager:
    """Manages the L0→L1→L2→L3 memory extraction pipeline.

    This is a direct Python port of TencentDB-Agent-Memory's
    MemoryPipelineManager, adapted for qclaw's file-based storage.

    Usage:
        mgr = MemoryPipelineManager(PipelineConfig())
        mgr.set_l1_runner(my_l1_runner)
        mgr.set_l2_runner(my_l2_runner)
        mgr.set_l3_runner(my_l3_runner)
        mgr.start()  # restores from checkpoint

        # On each conversation turn:
        mgr.notify_conversation("session-1", [CapturedMessage(...)])

        # On shutdown:
        mgr.destroy()
    """

    def __init__(
        self,
        config: PipelineConfig,
        data_dir: str = ".tdai_memory",
        session_filter: SessionFilter = None,
    ):
        self.cfg = config
        self.data_dir = data_dir
        self.checkpoint = CheckpointManager(data_dir)
        self.session_filter = session_filter or SessionFilter()

        # Convert to milliseconds internally
        self._l1_idle_timeout_s = config.l1_idle_timeout_seconds
        self._l2_delay_after_l1_s = config.l2_delay_after_l1_seconds
        self._l2_min_interval_s = config.l2_min_interval_seconds
        self._l2_max_interval_s = config.l2_max_interval_seconds
        self._session_active_window_s = config.l2_session_active_window_hours * 3600

        # Queues
        self.l1_queue = SerialQueue("L1")
        self.l2_queue = SerialQueue("L2")
        self.l3_queue = SerialQueue("L3")

        # L3 dedup
        self._l3_pending = False
        self._l3_running = False

        # Per-session state
        self._session_states: Dict[str, PipelineSessionState] = {}
        self._message_buffers: Dict[str, List[CapturedMessage]] = {}
        self._l2_last_run_time: Dict[str, float] = {}

        # Timer infrastructure
        self._destroyed = False
        self._timers_lock = threading.Lock()
        self._timers: Dict[str, Dict[str, ManagedTimer]] = {}  # sessionKey -> {"l1_idle": ..., "l2_schedule": ...}
        self._timer_queues: Dict[str, Dict[str, bool]] = {}    # sessionKey -> {"l1_queued": ..., "l2_queued": ...}
        self._l1_retry_counts: Dict[str, int] = {}

        # Runners (set via wiring)
        self._l1_runner: Optional[Callable] = None
        self._l2_runner: Optional[Callable] = None
        self._l3_runner: Optional[Callable] = None

        # GC
        self._notify_counter = 0

    def _is_destroyed_fn(self) -> bool:
        return self._destroyed

    # ============================
    # Setup
    # ============================

    def set_l1_runner(self, runner: Callable) -> None:
        """Set the L1 extraction runner: fn(session_key, messages) -> L1RunnerResult."""
        self._l1_runner = runner

    def set_l2_runner(self, runner: Callable) -> None:
        """Set the L2 scene extraction runner: fn(session_key, cursor) -> L2RunnerResult."""
        self._l2_runner = runner

    def set_l3_runner(self, runner: Callable) -> None:
        """Set the L3 persona generation runner: fn() -> None."""
        self._l3_runner = runner

    def start(self, restored_states: Dict[str, PipelineSessionState] = None) -> None:
        """Start the pipeline, restoring from checkpoint.

        Sessions with pending work are automatically re-enqueued.
        """
        if self._destroyed:
            return

        if restored_states is None:
            restored_states = self.checkpoint.get_all_pipeline_states()

        skipped = 0
        for session_key, state in restored_states.items():
            if self.session_filter.should_skip(session_key):
                skipped += 1
                continue
            # Backfill warmup_threshold for legacy sessions
            if not hasattr(state, 'warmup_threshold') or state.warmup_threshold is None:
                state.warmup_threshold = 1 if self.cfg.enable_warmup else 0
            self._session_states[session_key] = state

        logger.info(
            f"[pipeline] Restored {len(self._session_states)} session state(s)"
            + (f" (filtered {skipped} internal)" if skipped else "")
        )

        # Recovery: re-enqueue sessions with pending work
        self._recover_pending_sessions()
        logger.info("[pipeline] Pipeline started")

    # ============================
    # L0→L1: notifyConversation
    # ============================

    def notify_conversation(self, session_key: str, messages: List[CapturedMessage]) -> None:
        """Notify the pipeline that a conversation round ended.

        Buffers messages for L1 batch processing. Two trigger paths:
        - Path A (threshold): conversation_count >= effective threshold → immediate L1
        - Path B (idle): reset idle timer → L1 fires when user stops chatting
        """
        if self._destroyed:
            return
        if self.session_filter.should_skip(session_key):
            return

        state = self._get_or_create_state(session_key)
        state.conversation_count += 1
        state.last_active_time = time.time()

        # Reset retry count on new conversation
        self._l1_retry_counts[session_key] = 0

        # Buffer messages
        buffer = self._message_buffers.get(session_key, [])
        buffer.extend(messages)
        self._message_buffers[session_key] = buffer

        effective_threshold = self._get_effective_threshold(state)
        warmup_info = (
            f" (warmup: {state.warmup_threshold})"
            if self.cfg.enable_warmup and state.warmup_threshold > 0
            else ""
        )

        logger.debug(
            f"[pipeline] [{session_key}] notify: "
            f"conversation_count={state.conversation_count}/{effective_threshold}{warmup_info}, "
            f"buffered={len(buffer)} (+{len(messages)} new)"
        )

        self._persist_states()

        # Path A: threshold reached → trigger L1
        if state.conversation_count >= effective_threshold:
            logger.debug(
                f"[pipeline] [{session_key}] Threshold reached "
                f"({state.conversation_count}>={effective_threshold}{warmup_info}), triggering L1"
            )
            self._enqueue_l1(session_key, "threshold")
            return

        # Path B: reset idle timer
        self._reset_l1_idle_timer(session_key)

        # Periodic GC
        self._notify_counter += 1
        if self._notify_counter >= self.cfg.session_gc_every_n_notifications:
            self._notify_counter = 0
            self._gc_stale_sessions()

    # ============================
    # Session flush (scoped end-of-session)
    # ============================

    def flush_session(self, session_key: str) -> None:
        """Flush pending work for a single session.

        Used on session end (not process shutdown).
        Other sessions' timers and buffers remain untouched.
        """
        if self._destroyed:
            return
        if self.session_filter.should_skip(session_key):
            return

        # Cancel idle timer
        timers = self._timers.get(session_key, {})
        if "l1_idle" in timers and timers["l1_idle"].pending:
            timers["l1_idle"].cancel()

        # Flush buffered messages through L1
        buffer = self._message_buffers.get(session_key, [])
        if buffer:
            logger.debug(
                f"[pipeline] [{session_key}] flushSession: "
                f"enqueuing L1 for {len(buffer)} buffered message(s)"
            )
            self._enqueue_l1(session_key, "flush")

        # Wait for L1 to drain
        self.l1_queue.on_idle()
        logger.debug(f"[pipeline] [{session_key}] flushSession: complete")

    # ============================
    # Graceful shutdown
    # ============================

    DESTROY_TIMEOUT_S = 3.0

    def destroy(self) -> None:
        """Graceful shutdown with timeout protection.

        1. Mark destroyed, stop accepting new work.
        2. Flush pending L1/L2/L3 work within timeout.
        3. Always persist state for recovery on next startup.
        """
        if self._destroyed:
            return
        self._destroyed = True

        logger.info(f"[pipeline] Destroying (timeout={self.DESTROY_TIMEOUT_S}s)...")
        try:
            self._do_flush(timeout=self.DESTROY_TIMEOUT_S)
            logger.info("[pipeline] Pipeline flushed successfully")
        except Exception as e:
            logger.warning(
                f"[pipeline] Flush timed out or failed: {e}. "
                "Pending work will be recovered on next startup."
            )

        # Always persist state
        try:
            self._persist_states()
        except Exception as e:
            logger.error(f"[pipeline] Failed to persist states during destroy: {e}")

        logger.info("[pipeline] Pipeline destroyed")

    def _do_flush(self, timeout: float = 3.0) -> None:
        """Internal: attempt to flush all pending pipeline work."""
        # Step 1: Cancel all L1 idle timers and enqueue if buffered
        for session_key, timers in self._timers.items():
            if "l1_idle" in timers and timers["l1_idle"].pending:
                timers["l1_idle"].cancel()
                buffer = self._message_buffers.get(session_key, [])
                if buffer:
                    logger.debug(
                        f"[pipeline] [{session_key}] Flush: "
                        f"enqueuing L1 for {len(buffer)} buffered messages"
                    )
                    self._enqueue_l1(session_key, "flush")

        # Step 2: Wait for L1 queue
        self.l1_queue.on_idle(timeout=timeout / 3)

        # Step 3: Flush L2 schedule timers
        for session_key, timers in self._timers.items():
            if "l2_schedule" in timers and timers["l2_schedule"].pending:
                timers["l2_schedule"].flush()

        # Step 4: Wait for L2/L3 queues
        self.l2_queue.on_idle(timeout=timeout / 3)
        self.l3_queue.on_idle(timeout=timeout / 3)

    # ============================
    # Internal: L1 scheduling
    # ============================

    def _reset_l1_idle_timer(self, session_key: str) -> None:
        """Reset the L1 idle timer for a session."""
        timers = self._get_or_create_timers(session_key)
        timers["l1_idle"].schedule(self._l1_idle_timeout_s, lambda: self._on_l1_idle(session_key))

    def _on_l1_idle(self, session_key: str) -> None:
        """Called when L1 idle timer fires."""
        buffer = self._message_buffers.get(session_key, [])
        state = self._session_states.get(session_key)

        if (not buffer or len(buffer) == 0) and (not state or state.conversation_count == 0):
            logger.debug(f"[pipeline] [{session_key}] L1 idle timeout but nothing pending")
            return

        logger.debug(
            f"[pipeline] [{session_key}] L1 idle timeout fired "
            f"(buffered={len(buffer) if buffer else 0}, "
            f"conversations={state.conversation_count if state else 0})"
        )
        self._enqueue_l1(session_key, "idle_timeout")

    def _enqueue_l1(self, session_key: str, trigger_reason: str = "threshold") -> None:
        """Enqueue L1 extraction for a session."""
        queue_state = self._get_or_create_timer_queues(session_key)
        timers = self._get_or_create_timers(session_key)

        if queue_state.get("l1_queued", False):
            logger.debug(f"[pipeline] [{session_key}] L1 already queued, skipping")
            return

        # Cancel idle timer (threshold beat it)
        if "l1_idle" in timers:
            timers["l1_idle"].cancel()

        queue_state["l1_queued"] = True

        logger.debug(f"[pipeline] [{session_key}] Enqueuing L1 (reason={trigger_reason})")

        def _run_l1_wrapper():
            try:
                self._run_l1(session_key)
            except Exception:
                logger.exception(f"[pipeline] [{session_key}] L1 task failed")
            finally:
                queue_state["l1_queued"] = False

        self.l1_queue.add(_run_l1_wrapper)

    def _run_l1(self, session_key: str) -> None:
        """Execute L1 extraction: drain buffer, call runner, advance state."""
        state = self._session_states.get(session_key)
        if not state:
            return

        # Drain message buffer
        buffer = self._message_buffers.get(session_key, [])
        self._message_buffers[session_key] = []

        if len(buffer) == 0 and state.conversation_count == 0:
            logger.debug(f"[pipeline] [{session_key}] L1 skipped: nothing pending")
            return

        logger.debug(
            f"[pipeline] [{session_key}] L1 running: "
            f"messages={len(buffer)}, conversation_count={state.conversation_count}"
        )

        if not self._l1_runner:
            logger.warning(f"[pipeline] [{session_key}] No L1 runner set, skipping")
            state.l2_pending_l1_count = state.conversation_count
            state.conversation_count = 0
            self._advance_warmup(state)
            self._persist_states()
            self._advance_l2_timer(session_key)
            return

        try:
            self._l1_runner(session_key, buffer)
            logger.debug(f"[pipeline] [{session_key}] L1 complete: processed {len(buffer)} messages")
        except Exception:
            logger.exception(f"[pipeline] [{session_key}] L1 runner failed")
            # Restore messages to buffer for retry
            current = self._message_buffers.get(session_key, [])
            self._message_buffers[session_key] = buffer + current

            # Retry with backoff
            retry_count = self._l1_retry_counts.get(session_key, 0) + 1
            self._l1_retry_counts[session_key] = retry_count
            if retry_count <= self.cfg.l1_max_retries:
                logger.debug(
                    f"[pipeline] [{session_key}] L1 retry {retry_count}/{self.cfg.l1_max_retries} "
                    f"scheduled in {self.cfg.l1_retry_delay_seconds}s"
                )
                timers = self._get_or_create_timers(session_key)
                timers["l1_idle"].schedule(
                    self.cfg.l1_retry_delay_seconds,
                    lambda: self._on_l1_idle(session_key)
                )
            else:
                logger.warning(
                    f"[pipeline] [{session_key}] L1 max retries reached ({self.cfg.l1_max_retries}), "
                    f"giving up. {len(buffer) + len(current)} messages remain buffered."
                )
            return

        # Success: reset retry count
        self._l1_retry_counts[session_key] = 0

        # Advance state
        state.l2_pending_l1_count = state.conversation_count
        state.conversation_count = 0
        self._advance_warmup(state)
        self._persist_states()

        # Advance L2 timer
        self._advance_l2_timer(session_key)

    # ============================
    # Internal: L2 scheduling (downward-only timer)
    # ============================

    def _advance_l2_timer(self, session_key: str) -> None:
        """Advance L2 timer: fire after delay, but never earlier than minInterval floor."""
        if self._destroyed:
            return

        timers = self._get_or_create_timers(session_key)
        now = time.time()

        # Floor: lastL2 + minInterval
        last_l2 = self._l2_last_run_time.get(session_key, 0)
        min_floor = last_l2 + self._l2_min_interval_s if last_l2 > 0 else 0

        # Desired: now + delay, but no earlier than floor
        desired_time = max(now + self._l2_delay_after_l1_s, min_floor)

        advanced = timers["l2_schedule"].try_advance_to(
            desired_time,
            lambda: self._on_l2_fired(session_key, "delay-after-l1")
        )

        if advanced:
            delay = desired_time - now
            logger.debug(f"[pipeline] [{session_key}] L2 timer advanced: firing in {delay:.0f}s")
        else:
            logger.debug(f"[pipeline] [{session_key}] L2 timer not advanced: earlier schedule exists")

    def _arm_l2_max_interval(self, session_key: str) -> None:
        """Arm L2 timer for maxInterval guarantee."""
        if self._destroyed:
            return

        timers = self._get_or_create_timers(session_key)
        fire_at = time.time() + self._l2_max_interval_s
        timers["l2_schedule"].schedule_at(
            fire_at,
            lambda: self._on_l2_fired(session_key, "max-interval")
        )
        logger.debug(f"[pipeline] [{session_key}] L2 maxInterval armed: {self._l2_max_interval_s}s")

    def _on_l2_fired(self, session_key: str, source: str) -> None:
        """Called when L2 timer fires."""
        state = self._session_states.get(session_key)
        if not state:
            return

        # Cold session check (only for maxInterval triggers)
        if source == "max-interval":
            inactive_s = time.time() - state.last_active_time
            if inactive_s >= self._session_active_window_s:
                logger.debug(
                    f"[pipeline] [{session_key}] L2 timer fired but session cold "
                    f"(inactive {inactive_s/3600:.1f}h), timer stopped"
                )
                return

        self._enqueue_l2(session_key, f"timer:{source}")

    def _enqueue_l2(self, session_key: str, trigger: str) -> None:
        """Enqueue L2 scene extraction for a session."""
        queue_state = self._get_or_create_timer_queues(session_key)
        timers = self._get_or_create_timers(session_key)

        # Cancel pending L2 timer
        if "l2_schedule" in timers:
            timers["l2_schedule"].cancel()

        if queue_state.get("l2_queued", False):
            logger.warning(f"[pipeline] [{session_key}] L2 already queued (trigger={trigger}), skipping")
            return

        queue_state["l2_queued"] = True
        logger.debug(f"[pipeline] [{session_key}] Enqueuing L2 (trigger={trigger})")

        def _run_l2_wrapper():
            try:
                self._run_l2(session_key)
            except Exception:
                logger.exception(f"[pipeline] [{session_key}] L2 task failed")
            finally:
                queue_state["l2_queued"] = False

        self.l2_queue.add(_run_l2_wrapper)

    def _run_l2(self, session_key: str) -> None:
        """Execute L2 scene extraction."""
        state = self._session_states.get(session_key)
        if not state:
            return

        if not self._l2_runner:
            logger.warning(f"[pipeline] [{session_key}] No L2 runner set, skipping")
            return

        logger.debug(
            f"[pipeline] [{session_key}] L2 running: "
            f"l2_pending_l1_count={state.l2_pending_l1_count}"
        )

        cursor = state.last_extraction_updated_time or None

        try:
            self._l2_runner(session_key, cursor)
        except Exception:
            logger.exception(f"[pipeline] [{session_key}] L2 runner failed")
            self._arm_l2_max_interval(session_key)
            return

        # After L2: update state
        now = time.time()
        state.l2_pending_l1_count = 0
        state.last_extraction_time = time.strftime("%Y-%m-%dT%H:%M:%S")
        state.l2_last_extraction_time = state.last_extraction_time
        self._l2_last_run_time[session_key] = now

        self._persist_states()
        logger.debug(f"[pipeline] [{session_key}] L2 complete")

        # Arm maxInterval for next cycle
        self._arm_l2_max_interval(session_key)

        # Trigger L3
        self._trigger_l3()

    # ============================
    # Internal: L3 queue (global, dedup)
    # ============================

    def _trigger_l3(self) -> None:
        """Trigger L3 persona generation with dedup protection."""
        if self._destroyed:
            return

        if self._l3_running:
            self._l3_pending = True
            logger.debug("[pipeline] L3 already running, marking pending")
            return

        logger.debug("[pipeline] Triggering L3")
        self._enqueue_l3()

    def _enqueue_l3(self) -> None:
        """Enqueue L3 persona generation."""
        self._l3_running = True
        self._l3_pending = False

        logger.debug("[pipeline] Enqueuing L3")

        def _run_l3_wrapper():
            try:
                self._run_l3()
            except Exception:
                logger.exception("[pipeline] L3 task failed")
            finally:
                self._l3_running = False
                if self._l3_pending and not self._destroyed:
                    logger.debug("[pipeline] L3 has pending work, re-running")
                    self._enqueue_l3()

        self.l3_queue.add(_run_l3_wrapper)

    def _run_l3(self) -> None:
        """Execute L3 persona generation."""
        if not self._l3_runner:
            logger.warning("[pipeline] No L3 runner set, skipping")
            return

        logger.debug("[pipeline] L3 running")
        try:
            self._l3_runner()
            logger.debug("[pipeline] L3 complete")
        except Exception:
            logger.exception("[pipeline] L3 runner failed")

    # ============================
    # Internal: warm-up
    # ============================

    def _get_effective_threshold(self, state: PipelineSessionState) -> int:
        """Get L1 trigger threshold considering warm-up."""
        if not self.cfg.enable_warmup:
            return self.cfg.every_n_conversations
        if state.warmup_threshold <= 0:
            return self.cfg.every_n_conversations
        return min(state.warmup_threshold, self.cfg.every_n_conversations)

    def _advance_warmup(self, state: PipelineSessionState) -> None:
        """Advance warm-up threshold after successful L1."""
        if not self.cfg.enable_warmup:
            return
        if state.warmup_threshold <= 0:
            return  # already graduated

        next_val = state.warmup_threshold * 2
        if next_val >= self.cfg.every_n_conversations:
            state.warmup_threshold = 0  # graduated
            logger.debug("[pipeline] Warm-up graduated → steady-state")
        else:
            state.warmup_threshold = next_val
            logger.debug(f"[pipeline] Warm-up advanced → next={next_val}")

    # ============================
    # Internal: state management
    # ============================

    def _get_or_create_state(self, session_key: str) -> PipelineSessionState:
        state = self._session_states.get(session_key)
        if not state:
            warmup = 1 if self.cfg.enable_warmup else 0
            state = PipelineSessionState(
                last_active_time=time.time(),
                warmup_threshold=warmup,
            )
            self._session_states[session_key] = state
            logger.debug(f"[pipeline] [{session_key}] Created new session state")
        return state

    def _get_or_create_timers(self, session_key: str) -> Dict[str, ManagedTimer]:
        timers = self._timers.get(session_key)
        if not timers:
            timers = {
                "l1_idle": ManagedTimer(f"L1-idle:{session_key}", self._is_destroyed_fn),
                "l2_schedule": ManagedTimer(f"L2:{session_key}", self._is_destroyed_fn),
            }
            self._timers[session_key] = timers
        return timers

    def _get_or_create_timer_queues(self, session_key: str) -> Dict[str, bool]:
        qs = self._timer_queues.get(session_key)
        if not qs:
            qs = {"l1_queued": False, "l2_queued": False}
            self._timer_queues[session_key] = qs
        return qs

    def _persist_states(self) -> None:
        """Persist all session states to checkpoint."""
        self.checkpoint.merge_pipeline_states(self._session_states)

    # ============================
    # Internal: recovery
    # ============================

    def _recover_pending_sessions(self) -> None:
        """Re-enqueue sessions with pending work from before restart."""
        for session_key, state in self._session_states.items():
            if state.conversation_count == 0 and state.l2_pending_l1_count == 0:
                continue

            logger.debug(
                f"[pipeline] [{session_key}] Recovery: "
                f"conversation_count={state.conversation_count}, "
                f"l2_pending_l1_count={state.l2_pending_l1_count}, arming L2 timer"
            )

            state.l2_pending_l1_count = max(
                state.l2_pending_l1_count, state.conversation_count
            )
            state.conversation_count = 0
            self._advance_l2_timer(session_key)

    # ============================
    # Internal: GC
    # ============================

    def _gc_stale_sessions(self) -> None:
        """Evict cold sessions from memory."""
        now = time.time()
        max_inactive = self._session_active_window_s * self.cfg.session_gc_inactive_multiplier
        evicted = 0

        to_evict = []
        for session_key, state in self._session_states.items():
            if now - state.last_active_time < max_inactive:
                continue

            # Don't evict sessions with active work
            qs = self._timer_queues.get(session_key, {})
            if qs.get("l1_queued") or qs.get("l2_queued"):
                continue

            buffer = self._message_buffers.get(session_key, [])
            if buffer:
                continue

            to_evict.append(session_key)

        for session_key in to_evict:
            # Cancel timers
            timers = self._timers.pop(session_key, {})
            for t in timers.values():
                t.cancel()

            self._session_states.pop(session_key, None)
            self._message_buffers.pop(session_key, None)
            self._timer_queues.pop(session_key, None)
            self._l2_last_run_time.pop(session_key, None)
            evicted += 1

        if evicted > 0:
            logger.debug(
                f"[pipeline] Session GC: evicted {evicted} cold session(s), "
                f"{len(self._session_states)} remaining"
            )

    # ============================
    # Public accessors
    # ============================

    def get_session_state(self, session_key: str) -> Optional[PipelineSessionState]:
        return self._session_states.get(session_key)

    def get_buffered_count(self, session_key: str) -> int:
        return len(self._message_buffers.get(session_key, []))

    def get_session_keys(self) -> List[str]:
        return list(self._session_states.keys())

    @property
    def is_destroyed(self) -> bool:
        return self._destroyed

    def get_queue_sizes(self) -> dict:
        return {
            "l1_size": self.l1_queue.size,
            "l2_size": self.l2_queue.size,
            "l3_size": self.l3_queue.size,
            "l1_pending": self.l1_queue.pending,
            "l2_pending": self.l2_queue.pending,
            "l3_pending": self.l3_queue.pending,
        }


# ============================
# Convenience: create default pipeline
# ============================

def create_default_pipeline(
    data_dir: str = ".tdai_memory",
    every_n: int = 5,
    enable_warmup: bool = True,
    l1_idle_timeout: int = 600,
    l2_min_interval: int = 900,
    l2_max_interval: int = 3600,
) -> MemoryPipelineManager:
    """Create a MemoryPipelineManager with sensible defaults."""
    config = PipelineConfig(
        every_n_conversations=every_n,
        enable_warmup=enable_warmup,
        l1_idle_timeout_seconds=l1_idle_timeout,
        l2_min_interval_seconds=l2_min_interval,
        l2_max_interval_seconds=l2_max_interval,
    )
    return MemoryPipelineManager(config, data_dir)


# ============================
# L1 Runner: integration with evolver.py
# ============================

def create_l1_runner(workspace_dir: str):
    """Create an L1 runner that extracts Agent facts from buffered messages.

    Integrates with evolver.py's record_agent_fact() for structured fact extraction.

    Args:
        workspace_dir: Path to qclaw workspace (for evolver.py import)

    Returns:
        A callable L1 runner: fn(session_key, messages) -> None
    """
    import sys
    if workspace_dir not in sys.path:
        sys.path.insert(0, workspace_dir)

    try:
        from evolver import record_agent_fact
    except ImportError:
        logger.warning("[pipeline] evolver.py not found, L1 runner will be no-op")
        record_agent_fact = None

    def run_l1(session_key: str, messages: List[CapturedMessage]) -> None:
        """Extract structured facts from buffered messages."""
        if not messages:
            return

        # Build a summary of the conversation batch
        user_msgs = [m for m in messages if m.role == "user"]
        assistant_msgs = [m for m in messages if m.role == "assistant"]

        # Extract one fact per user-assistant pair (simplified)
        for user_msg in user_msgs:
            # Find matching assistant response (rough pairing)
            user_ts = user_msg.timestamp
            responses = [
                m for m in assistant_msgs
                if m.timestamp >= user_ts
            ]

            task_summary = f"user@{session_key}: {user_msg.content[:200]}"
            response_summary = responses[0].content[:200] if responses else "(no response)"

            if record_agent_fact:
                try:
                    record_agent_fact(
                        task=task_summary,
                        method=f"conv@{session_key}",
                        success=True,
                        notes=f"response: {response_summary}",
                    )
                except Exception:
                    logger.exception(f"[pipeline] L1 fact recording failed for {session_key}")

        logger.info(
            f"[pipeline] L1 extraction: {len(messages)} messages → "
            f"{len(user_msgs)} potential facts for session '{session_key}'"
        )

    return run_l1


# ============================
# L3 Runner: persona generation stub
# ============================

def create_l3_runner(workspace_dir: str, output_path: str = None):
    """Create an L3 runner that generates/updates persona from MEMORY.md patterns.

    Args:
        workspace_dir: Path to qclaw workspace
        output_path: Path to write persona file (default: workspace/persona_tdai.md)

    Returns:
        A callable L3 runner: fn() -> None
    """
    if output_path is None:
        output_path = os.path.join(workspace_dir, "persona_tdai.md")

    def run_l3() -> None:
        """Generate persona from accumulated memory facts."""
        memory_path = os.path.join(workspace_dir, "MEMORY.md")
        facts_path = os.path.join(workspace_dir, ".evolver_facts.jsonl")

        stats = {
            "memory_exists": os.path.exists(memory_path),
            "facts_exists": os.path.exists(facts_path),
        }

        if stats["facts_exists"]:
            try:
                with open(facts_path, "r", encoding="utf-8") as f:
                    facts_count = sum(1 for _ in f)
                stats["facts_count"] = facts_count
            except Exception:
                stats["facts_count"] = 0

        # Generate persona summary
        lines = [
            "# Persona (TDAI L3)",
            f"",
            f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
            f"## Statistics",
            f"- MEMORY.md exists: {stats['memory_exists']}",
            f"- Agent facts count: {stats.get('facts_count', 0)}",
            f"",
            f"## Note",
            f"Full persona generation requires LLM integration. ",
            f"This stub records statistics. Upgrade to LLM-based extraction for full L3.",
        ]

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"[pipeline] L3 persona stub written to {output_path}")

    return run_l3


# ============================
# CLI
# ============================

if __name__ == "__main__":
    # Demo: create pipeline, simulate conversations, verify scheduling
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"=== TDAI Memory Pipeline Demo ===")
        print(f"Data dir: {tmpdir}")

        mgr = create_default_pipeline(data_dir=tmpdir, every_n=3, l1_idle_timeout=5)

        # Wire up stub runners
        l1_count = [0]

        def stub_l1(session_key, messages):
            l1_count[0] += len(messages)
            print(f"  L1[{session_key}]: extracted from {len(messages)} messages (total={l1_count[0]})")

        def stub_l2(session_key, cursor):
            print(f"  L2[{session_key}]: scene extraction (cursor={cursor})")

        def stub_l3():
            print(f"  L3: persona generation")

        mgr.set_l1_runner(stub_l1)
        mgr.set_l2_runner(stub_l2)
        mgr.set_l3_runner(stub_l3)
        mgr.start()

        # Simulate 10 conversation rounds
        import datetime
        for i in range(10):
            ts = datetime.datetime.now().isoformat()
            msg = CapturedMessage(
                role="user",
                content=f"Message {i}: What's the weather?",
                timestamp=ts,
            )
            mgr.notify_conversation("demo-session", [msg])
            time.sleep(0.5)

        print(f"\nQueue sizes: {mgr.get_queue_sizes()}")
        print(f"Sessions: {mgr.get_session_keys()}")

        # Wait for queues to drain
        print("Waiting for queues to drain...")
        mgr.l1_queue.on_idle(timeout=5.0)
        mgr.l2_queue.on_idle(timeout=5.0)
        mgr.l3_queue.on_idle(timeout=5.0)

        print(f"Final queue sizes: {mgr.get_queue_sizes()}")
        print(f"Total L1 processed: {l1_count[0]}")

        mgr.destroy()
        print("=== Demo complete ===")