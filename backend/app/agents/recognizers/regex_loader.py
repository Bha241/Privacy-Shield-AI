from pathlib import Path
import yaml
import re


class RegexLoader:

    def __init__(self):

        config_path = (
            Path(__file__)
            .resolve()
            .parent.parent
            / "config_pattern"
            / "patterns.yaml"
        )

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self.patterns = {}

        for label, info in data.items():
            # DOB is handled by StructuredRecognizer, which validates calendar
            # dates. Do not retain the legacy shape-only rule here because it
            # accepts impossible values such as 31/02/1990.
            if label == "DATE_OF_BIRTH":
                continue
            self.patterns[label] = {
                "regex": re.compile(info["regex"], re.IGNORECASE),
                "confidence": info["confidence"],
                "domains": info.get("domains", ["all", "general"])
            }

    def get_patterns(self, domain: str = "general"):
        domain_norm = (domain or "general").strip().lower().replace(" ", "_").replace("-", "_")
        if domain_norm in ("general", "all"):
            return self.patterns

        filtered = {}
        for label, info in self.patterns.items():
            p_domains = [d.lower() for d in info.get("domains", ["all"])]
            if "all" in p_domains or "general" in p_domains or domain_norm in p_domains:
                filtered[label] = info
        return filtered
