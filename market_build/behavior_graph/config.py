from __future__ import annotations

from dataclasses import dataclass


DEFAULT_MIN_ENDPOINT_USERS = 100
DEFAULT_MIN_SHARED_USERS = 5


@dataclass(frozen=True)
class BehaviorGraphRules:
    """共评图的版本化强边规则。

    这两个阈值沿用此前 Electronics 实验口径：
    - 每个端点至少 100 个不同用户；
    - 商品对至少 5 个共同用户。
    """

    min_endpoint_users: int = DEFAULT_MIN_ENDPOINT_USERS
    min_shared_users: int = DEFAULT_MIN_SHARED_USERS

    def validate(self) -> None:
        if self.min_endpoint_users <= 0:
            raise ValueError("min_endpoint_users must be positive")
        if self.min_shared_users <= 0:
            raise ValueError("min_shared_users must be positive")

    def as_dict(self) -> dict[str, int]:
        self.validate()
        return {
            "min_endpoint_users": self.min_endpoint_users,
            "min_shared_users": self.min_shared_users,
        }
