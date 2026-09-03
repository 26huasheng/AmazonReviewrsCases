from __future__ import annotations

from dataclasses import dataclass


DEFAULT_MIN_ENDPOINT_USERS = 100
DEFAULT_MIN_SHARED_USERS = 5
DEFAULT_MAX_COMPETITORS = 16


@dataclass(frozen=True)
class BehaviorGraphRules:
    """正式 Case 使用的 focal-centered 共评筛选规则。

    共评阈值沿用此前 Electronics 预实验：
    - focal / competitor 各自至少 100 个不同用户；
    - focal 与 competitor 至少 5 个共同用户。

    `max_competitors=16` 固定为当前 benchmark 第一版的 Case 竞品上限：
    - <=16 个竞品时全部保留；
    - >16 个竞品时才启动 pre-t0 共评优先筛选。
    """

    min_endpoint_users: int = DEFAULT_MIN_ENDPOINT_USERS
    min_shared_users: int = DEFAULT_MIN_SHARED_USERS
    max_competitors: int = DEFAULT_MAX_COMPETITORS

    def validate(self) -> None:
        if self.min_endpoint_users <= 0:
            raise ValueError("min_endpoint_users must be positive")
        if self.min_shared_users <= 0:
            raise ValueError("min_shared_users must be positive")
        if self.max_competitors <= 0:
            raise ValueError("max_competitors must be positive")

    def as_dict(self) -> dict[str, int]:
        self.validate()
        return {
            "min_endpoint_users": self.min_endpoint_users,
            "min_shared_users": self.min_shared_users,
            "max_competitors": self.max_competitors,
        }
