from pathlib import Path

import yaml
from pydantic import BaseModel

POLICY_PATH = Path(__file__).resolve().parent.parent / "policy.yaml"


class Thresholds(BaseModel):
    medium: float = 25.0
    high: float = 50.0
    critical: float = 75.0


class PolicyConfig(BaseModel):
    thresholds: Thresholds = Thresholds()
    blocked_categories: list[str] = []
    allowed_platforms: list[str] = []

    def is_platform_allowed(self, platform: str) -> bool:
        if not self.allowed_platforms:
            return True
        return platform.lower() in self.allowed_platforms

    def blocked_categories_present(self, categories: set[str]) -> list[str]:
        return sorted(categories & set(self.blocked_categories))


def load_policy(path: Path = POLICY_PATH) -> PolicyConfig:
    if not path.exists():
        return PolicyConfig()
    data = yaml.safe_load(path.read_text()) or {}
    return PolicyConfig(**data)


policy = load_policy()
