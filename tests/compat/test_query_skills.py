"""
Suite: QuerySkill (ACP spec §8)
Tests /skills endpoint for runtime capability introspection.
"""
from compat_base import Compat


class QuerySkillsSuite(Compat):
    SUITE_NAME = "QuerySkill"

    def run(self) -> None:
        s, r = self.get("/skills")

        self.check("GET /skills returns 200",
                   s == 200, "MUST",
                   f"got {s}")

        self.check("/skills returns a list",
                   isinstance(r, list), "MUST",
                   f"got {type(r).__name__}")

        if isinstance(r, list) and len(r) > 0:
            skill = r[0]
            self.check("/skills[0] has 'name'",
                       isinstance(skill.get("name"), str), "MUST")
            self.check("/skills[0] has 'description'",
                       isinstance(skill.get("description"), str), "SHOULD")
            self.check("/skills[0] has 'version'",
                       "version" in skill, "SHOULD")
        elif isinstance(r, list):
            self.skip("/skills items have required fields",
                      "empty skills list (valid — agent may have no declared skills)")
        else:
            self.check("/skills items have required fields", False, "MUST",
                       "non-list response")
