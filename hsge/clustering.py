"""Online, nonparametric clustering for the growing skill library.

Why not k-means: you don't know the number of skills a priori and the library
must *grow* as exploration finds new behaviours. This is a streaming DP-means
variant on L2-normalized vectors (so cosine similarity == dot product):

    for each incoming point x:
        if max_j cos(x, c_j) >= sim_threshold:  assign to argmax cluster
        else:                                    spawn a new cluster at x

Centroids are maintained as an incremental (re-normalized) mean. We also do
optional online merging of clusters whose centroids have drifted within
threshold, which keeps the library from fragmenting.

The single hyperparameter `sim_threshold` is interpretable (a cosine cutoff),
which is exactly what you want when a reviewer asks "why this k?" — there is no k.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Cluster:
    cluster_id: int
    centroid: np.ndarray            # L2-normalized
    member_ids: list[str] = field(default_factory=list)
    count: int = 0

    def add(self, vec: np.ndarray, item_id: str) -> None:
        # incremental mean, then renormalize back onto the unit sphere
        self.count += 1
        self.centroid = self.centroid + (vec - self.centroid) / self.count
        n = np.linalg.norm(self.centroid)
        if n > 0:
            self.centroid = self.centroid / n
        self.member_ids.append(item_id)


class OnlineClusterer:
    def __init__(self, sim_threshold: float = 0.6, merge_threshold: float = 0.9):
        self.sim_threshold = sim_threshold
        self.merge_threshold = merge_threshold
        self.clusters: dict[int, Cluster] = {}
        self._next_id = 0

    def _matrix(self) -> tuple[list[int], np.ndarray] | tuple[list, None]:
        if not self.clusters:
            return [], None
        ids = list(self.clusters.keys())
        mat = np.vstack([self.clusters[i].centroid for i in ids])
        return ids, mat

    def nearest(self, vec: np.ndarray) -> tuple[int | None, float]:
        """Peek at the closest cluster without mutating anything: return its id
        and cosine similarity, or (None, 0.0) when the clusterer is empty. Lets a
        caller (e.g. PredicateRegistry) interpose its own decision between finding
        the nearest cluster and committing the vector to one."""
        ids, mat = self._matrix()
        if mat is None:
            return None, 0.0
        sims = mat @ vec
        best = int(np.argmax(sims))
        return ids[best], float(sims[best])

    def add_to(self, cid: int, vec: np.ndarray, item_id: str) -> int:
        """Force-assign a vector to an existing cluster (caller decided it belongs)."""
        self.clusters[cid].add(vec, item_id)
        self._maybe_merge(cid)
        return cid

    def spawn(self, vec: np.ndarray, item_id: str) -> int:
        """Force a brand-new cluster seeded at `vec`."""
        cid = self._next_id
        self._next_id += 1
        c = Cluster(cluster_id=cid, centroid=vec.copy())
        c.add(vec, item_id)            # sets count=1 and member list
        # add() above re-applies incremental mean from the seeded centroid; reset
        c.centroid = vec.copy()
        self.clusters[cid] = c
        return cid

    def partial_fit(self, vec: np.ndarray, item_id: str) -> int:
        """Assign one vector; return the cluster id it landed in (new or existing)."""
        cid, sim = self.nearest(vec)
        if cid is not None and sim >= self.sim_threshold:
            return self.add_to(cid, vec, item_id)
        return self.spawn(vec, item_id)

    def _maybe_merge(self, cid: int) -> None:
        """Merge `cid` into another cluster if their centroids are very close."""
        moved = self.clusters[cid]
        for other_id, other in list(self.clusters.items()):
            if other_id == cid:
                continue
            if float(moved.centroid @ other.centroid) >= self.merge_threshold:
                # fold the smaller into the larger
                small, big = sorted((moved, other), key=lambda c: c.count)
                big.member_ids.extend(small.member_ids)
                total = big.count + small.count
                big.centroid = (big.centroid * big.count + small.centroid * small.count) / total
                n = np.linalg.norm(big.centroid)
                if n > 0:
                    big.centroid /= n
                big.count = total
                del self.clusters[small.cluster_id]
                return

    def cluster_members(self, cid: int) -> list[str]:
        return self.clusters[cid].member_ids

    def __len__(self) -> int:
        return len(self.clusters)
