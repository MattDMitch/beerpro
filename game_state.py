# game_state.py — Core game logic and state management

import asyncio
import time
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Callable, Awaitable
import config


@dataclass
class MatchRecord:
    """Stores the result of a completed game."""
    winner: str
    score_t1: int
    score_t2: int
    duration_seconds: float
    point_history: List[Tuple[int, int]]  # sequence of (t1, t2) snapshots


class GameState:
    """
    Central game state. Thread-safe via asyncio.
    All mutations happen via async methods which also trigger broadcasts.
    """

    def __init__(self) -> None:
        # Current game
        self.team1_name: str = config.DEFAULT_TEAM1_NAME
        self.team2_name: str = config.DEFAULT_TEAM2_NAME
        self.score_t1: int = 0
        self.score_t2: int = 0
        self.point_history: List[Tuple[int, int]] = [(0, 0)]
        self.game_over: bool = False
        self.winner: Optional[str] = None
        self.game_start_time: float = time.time()

        # Match (across games this session)
        self.match_wins_t1: int = 0
        self.match_wins_t2: int = 0
        self.match_history: List[MatchRecord] = []

        # Replay state
        self.replay_active: bool = False

        # Setup mode — True until WiFi is configured
        self.setup_mode: bool = False

        # Broadcast callback — set by server.py after startup
        self._broadcast_fn: Optional[Callable[[dict], Awaitable[None]]] = None

        # asyncio lock to serialise state mutations
        self._lock = asyncio.Lock()

    def set_broadcast(self, fn: Callable[[dict], Awaitable[None]]) -> None:
        """Register the async broadcast function from the server."""
        self._broadcast_fn = fn

    def set_setup_mode(self, active: bool) -> None:
        """Enable or disable setup mode."""
        self.setup_mode = active

    async def _broadcast(self, msg: dict) -> None:
        if self._broadcast_fn:
            await self._broadcast_fn(msg)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    async def update_settings(self, team1: str, team2: str) -> None:
        async with self._lock:
            self.team1_name = team1.strip() or config.DEFAULT_TEAM1_NAME
            self.team2_name = team2.strip() or config.DEFAULT_TEAM2_NAME
        await self._broadcast(self._settings_msg())

    def _settings_msg(self) -> dict:
        return {
            "type": "settings",
            "team1": self.team1_name,
            "team2": self.team2_name,
            "match": [self.match_wins_t1, self.match_wins_t2],
        }

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    async def score_up(self, team: int) -> None:
        """Award a point to team (1 or 2). No-op if game is over or replay active."""
        async with self._lock:
            if self.game_over or self.replay_active:
                return
            if team == 1:
                self.score_t1 += 1
            else:
                self.score_t2 += 1
            self.point_history.append((self.score_t1, self.score_t2))
            self._check_win()
        await self._broadcast_score()

    async def score_down(self, team: int) -> None:
        """Remove a point from team (1 or 2), clamped at 0. No-op if game over or replay."""
        async with self._lock:
            if self.game_over or self.replay_active:
                return
            if team == 1:
                self.score_t1 = max(0, self.score_t1 - 1)
            else:
                self.score_t2 = max(0, self.score_t2 - 1)
            self.point_history.append((self.score_t1, self.score_t2))
        await self._broadcast_score()

    def _check_win(self) -> None:
        """Called inside lock. Sets game_over/winner if win condition is met."""
        t1, t2 = self.score_t1, self.score_t2
        target = config.TARGET_SCORE
        margin = config.WIN_BY
        if (t1 >= target or t2 >= target) and abs(t1 - t2) >= margin:
            self.game_over = True
            self.winner = self.team1_name if t1 > t2 else self.team2_name

    async def _broadcast_score(self) -> None:
        if self.game_over:
            # Update match wins
            if self.winner == self.team1_name:
                self.match_wins_t1 += 1
            else:
                self.match_wins_t2 += 1
            # Archive this game
            self.match_history.append(MatchRecord(
                winner=self.winner,
                score_t1=self.score_t1,
                score_t2=self.score_t2,
                duration_seconds=time.time() - self.game_start_time,
                point_history=list(self.point_history),
            ))
            await self._broadcast({
                "type": "game_over",
                "winner": self.winner,
                "score": [self.score_t1, self.score_t2],
                "match": [self.match_wins_t1, self.match_wins_t2],
            })
        else:
            await self._broadcast({
                "type": "score",
                "t1": self.score_t1,
                "t2": self.score_t2,
                "history": list(self.point_history),
                "team1": self.team1_name,
                "team2": self.team2_name,
            })

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    async def reset_game(self) -> None:
        """Reset scores for a new game. Match wins persist for the session."""
        async with self._lock:
            self.score_t1 = 0
            self.score_t2 = 0
            self.point_history = [(0, 0)]
            self.game_over = False
            self.winner = None
            self.game_start_time = time.time()
            self.replay_active = False
        await self._broadcast({
            "type": "reset",
            "team1": self.team1_name,
            "team2": self.team2_name,
            "match": [self.match_wins_t1, self.match_wins_t2],
        })

    async def reset_match(self) -> None:
        """Full reset including match wins. Called from settings page."""
        async with self._lock:
            self.score_t1 = 0
            self.score_t2 = 0
            self.point_history = [(0, 0)]
            self.game_over = False
            self.winner = None
            self.game_start_time = time.time()
            self.replay_active = False
            self.match_wins_t1 = 0
            self.match_wins_t2 = 0
            self.match_history = []
        await self._broadcast({
            "type": "reset",
            "team1": self.team1_name,
            "team2": self.team2_name,
            "match": [0, 0],
        })

    # ------------------------------------------------------------------
    # Replay
    # ------------------------------------------------------------------

    async def start_replay(self) -> None:
        async with self._lock:
            self.replay_active = True
        await self._broadcast({"type": "replay_start"})

    async def stop_replay(self) -> None:
        async with self._lock:
            self.replay_active = False
        await self._broadcast({"type": "replay_stop"})

    # ------------------------------------------------------------------
    # Input dispatcher — called by input_handler.py
    # ------------------------------------------------------------------

    async def handle_key(self, key: str) -> None:
        """Route a key event to the appropriate action."""
        # During replay: any key stops it
        if self.replay_active:
            await self.stop_replay()
            return

        # After game over: any key resets for new game
        if self.game_over:
            await self.reset_game()
            return

        # Normal game input
        if key == config.KEY_T1_UP:
            await self.score_up(1)
        elif key == config.KEY_T1_DOWN:
            await self.score_down(1)
        elif key == config.KEY_T2_UP:
            await self.score_up(2)
        elif key == config.KEY_T2_DOWN:
            await self.score_down(2)
        elif key == config.KEY_REPLAY:
            await self.start_replay()

    # ------------------------------------------------------------------
    # Snapshot for initial WebSocket sync
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Full state snapshot sent to newly connected WebSocket clients."""
        if self.setup_mode:
            return {"type": "setup_mode"}
        if self.game_over:
            return {
                "type": "game_over",
                "winner": self.winner,
                "score": [self.score_t1, self.score_t2],
                "match": [self.match_wins_t1, self.match_wins_t2],
                "team1": self.team1_name,
                "team2": self.team2_name,
            }
        if self.replay_active:
            return {"type": "replay_start"}
        return {
            "type": "score",
            "t1": self.score_t1,
            "t2": self.score_t2,
            "history": list(self.point_history),
            "team1": self.team1_name,
            "team2": self.team2_name,
            "match": [self.match_wins_t1, self.match_wins_t2],
        }


# Singleton instance shared across all modules
state = GameState()
