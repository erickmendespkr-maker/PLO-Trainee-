"""Offline-only fold and stack evidence fusion from recorded-video observations.

Independent implementation inspired by the visual detection approach described
in Baivaras/poker-data-scraper. No live capture, room connection or model reuse.
"""
from dataclasses import dataclass, field
from typing import Optional
import math
import re

def fold_label_candidate(text: str) -> bool:
    if not isinstance(text, str):
        raise TypeError("OCR text must be a string")
    return bool(re.search(r"(?<![A-Z])FOLD(?![A-Z])", text, re.I))

def valid(value):
    return type(value) in (int, float) and math.isfinite(value)

@dataclass(frozen=True)
class Observation:
    pts: float
    stack_bb: Optional[float] = None
    bet_bb: Optional[float] = None
    fold_label: bool = False
    cards_visible: Optional[bool] = None
    new_deal: bool = False

@dataclass
class FoldEvidence:
    table_id: str
    started_pts: float
    ended_pts: Optional[float] = None
    fold_pts: Optional[float] = None
    committed_bb: float = 0.0
    status: str = "OPEN"
    evidence: list = field(default_factory=list)
    incomplete_contributions: bool = False

    @property
    def loss_over_30bb(self) -> bool:
        """Candidate only, never a verified financial result."""
        return self.fold_pts is not None and self.committed_bb > 30

class OfflineFoldTracker:
    """One independent tracker per table; consume ordered video media PTS."""

    def __init__(self, table_id: str, start_pts: float, bb_noise: float = 0.5):
        if not isinstance(table_id, str) or not table_id or not valid(start_pts) or not valid(bb_noise) or bb_noise < 0:
            raise ValueError("invalid tracker configuration")
        self.hand = FoldEvidence(table_id, start_pts)
        self.last_pts = start_pts
        self.last_stack = None
        self.pending_delta = None
        self.pending_count = 0
        self.pending_fold_pts = None
        self.pending_fold_count = 0
        self.bb_noise = bb_noise
        self.ocr_gap = False

    def feed(self, obs: Observation) -> FoldEvidence:
        if not isinstance(obs, Observation) or not valid(obs.pts) or obs.pts < self.last_pts:
            raise ValueError("PTS must be finite and monotonic")
        if self.hand.ended_pts is not None:
            raise ValueError("hand already closed")
        for v in (obs.stack_bb, obs.bet_bb):
            if v is not None and (not valid(v) or v < 0):
                raise ValueError("invalid blind amount")
        self.last_pts = obs.pts
        if obs.new_deal:
            self.hand.ended_pts = obs.pts
            self.hand.status = "FOLDED_CANDIDATE_LOSS" if self.hand.fold_pts is not None else "UNRESOLVED"
            self.hand.evidence.append(("next_deal_verified_by_upstream", obs.pts))
            return self.hand

        if obs.stack_bb is None:
            self.ocr_gap = True
            self.pending_delta = None
            self.pending_count = 0
            self.hand.incomplete_contributions = True
            self.hand.evidence.append(("stack_ocr_missing", obs.pts))
        elif self.last_stack is None:
            self.last_stack = obs.stack_bb
            self.ocr_gap = False
        elif self.ocr_gap:
            self.last_stack = obs.stack_bb
            self.ocr_gap = False
            self.hand.evidence.append(("stack_baseline_reset_after_gap", obs.pts))
        elif self.hand.fold_pts is None:
            delta = self.last_stack - obs.stack_bb
            if delta > self.bb_noise:
                if self.pending_delta is not None and abs(delta - self.pending_delta) <= self.bb_noise:
                    self.pending_count += 1
                else:
                    self.pending_delta, self.pending_count = delta, 1
                if self.pending_count >= 2:
                    self.hand.committed_bb += delta
                    self.hand.evidence.append(("stable_stack_decrease_candidate", obs.pts, delta))
                    self.last_stack = obs.stack_bb
                    self.pending_delta, self.pending_count = None, 0
            else:
                self.pending_delta, self.pending_count = None, 0
                if delta < -self.bb_noise:
                    self.hand.incomplete_contributions = True
                    self.hand.evidence.append(("stack_increase_unexplained", obs.pts))
                    self.last_stack = obs.stack_bb

        if obs.fold_label and self.hand.fold_pts is None:
            if self.pending_fold_count == 0:
                self.pending_fold_pts = obs.pts
            self.pending_fold_count += 1
            if self.pending_fold_count >= 2:
                self.hand.fold_pts = self.pending_fold_pts
                self.hand.status = "FOLDED_CANDIDATE_LOSS"
                self.hand.evidence.append(("fold_label_stable_candidate", obs.pts))
        elif self.hand.fold_pts is None:
            self.pending_fold_count = 0
            self.pending_fold_pts = None
            if obs.cards_visible is False:
                self.hand.evidence.append(("cards_absent_not_proof_of_fold", obs.pts))
        return self.hand
