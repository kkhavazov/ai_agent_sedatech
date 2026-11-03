"""Verify the live prompt clock without loading models or external services."""
import ast
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import Mock
from zoneinfo import ZoneInfo


class CurrentDateTests(unittest.TestCase):
    def test_prompt_refreshes_across_berlin_midnight(self):
        source = Path(__file__).parents[1] / "customer_support_agent.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        prompt = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.FunctionDef) and node.name == "dated_prompt")
        prompt.decorator_list = []
        clock = Mock()
        scope = {"datetime": clock, "ZoneInfo": ZoneInfo, "system_prompt": "Routing rules"}
        exec(compile(ast.Module(body=[prompt], type_ignores=[]), str(source), "exec"), scope)
        for utc_hour, expected_date in [(22, "2026-11-02"), (23, "2026-11-03")]:
            instant = datetime(2026, 11, 2, utc_hour, 30, tzinfo=timezone.utc)
            clock.now.side_effect = lambda tz: instant.astimezone(tz)
            result = scope["dated_prompt"](None)
            self.assertIn(f"Current date in Europe/Berlin: {expected_date}", result)
            self.assertIn("+01:00", result)
            self.assertIn("Routing rules", result)


if __name__ == "__main__":
    unittest.main()
