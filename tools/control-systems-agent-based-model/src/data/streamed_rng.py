"""src/data/streamed_rng.py

Per-entity stream isolation for marginal value analysis.

Each named stream is an independent random.Random instance seeded
deterministically from SHA-256(master_seed + stream_name). Removing an
agent only eliminates that agent's streams — all other streams produce
identical sequences, enabling valid per-seed counterfactual comparison.

This is NOT Common Random Numbers (CRN), which synchronises a single
shared stream across paired runs. This is independent stream splitting:
each entity (agent, processor subsystem) gets its own isolated PRNG so
counterfactual comparisons are clean without requiring synchronisation.

See STREAM_ISOLATION.md for the full design rationale.

Reference: Glasserman, Monte Carlo Methods in Financial Engineering, ch. 4.
"""

from __future__ import annotations

import hashlib
import random
from typing import Dict


class StreamedRNG:
    """Provides named, independent PRNG streams derived from a master seed."""

    def __init__(self, master_seed: int):
        self._master_seed = int(master_seed)
        self._streams: Dict[str, random.Random] = {}

    def get(self, name: str) -> random.Random:
        """Get or create a named PRNG stream.

        The stream is seeded with a deterministic hash of
        (master_seed, name), so the same master seed + name
        always produces the same sequence regardless of creation order.
        """
        if name not in self._streams:
            derived = self._derive_seed(name)
            self._streams[name] = random.Random(derived)
        return self._streams[name]

    def agent_rng(self, subsystem: str, agent_id: str) -> random.Random:
        """Convenience: per-agent stream within a subsystem.

        Example: agent_rng("efficacy", "LEC001") -> stream "efficacy:LEC001"
        """
        return self.get(f"{subsystem}:{agent_id}")

    def _derive_seed(self, name: str) -> int:
        """Deterministic seed derivation using SHA-256.

        Using a cryptographic hash ensures no accidental correlation
        between streams even for similar names.
        """
        payload = f"{self._master_seed}:{name}".encode("utf-8")
        digest = hashlib.sha256(payload).digest()
        return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF
