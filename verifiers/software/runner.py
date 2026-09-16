"""在隔离进程中运行固定验收测试；从不根据合同执行任意命令。"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path


def main():
    mode, root_arg = sys.argv[1:]
    root = Path(root_arg)
    if mode == "trusted-acceptance-tests":
        spec = importlib.util.spec_from_file_location("subject_retry_config", root / "src/retry_config.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class Boundaries(unittest.TestCase):
            def test_zero(self):
                self.assertEqual(module.validate_retry_count(0), 0)

            def test_positive(self):
                self.assertEqual(module.validate_retry_count(3), 3)

            def test_negative(self):
                with self.assertRaises(ValueError):
                    module.validate_retry_count(-1)

            def test_bool(self):
                for value in (True, False):
                    with self.subTest(value=value), self.assertRaises(TypeError):
                        module.validate_retry_count(value)

            def test_string(self):
                with self.assertRaises(TypeError):
                    module.validate_retry_count("3")

            def test_float(self):
                with self.assertRaises(TypeError):
                    module.validate_retry_count(3.0)

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Boundaries)
    elif mode == "project-tests":
        sys.path.insert(0, str(root))
        suite = unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_*.py")
    else:
        raise ValueError("未注册检查")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    success = result.wasSuccessful() and result.testsRun > 0 and not result.skipped
    print(json.dumps({"mode": mode, "tests_run": result.testsRun, "skipped": len(result.skipped),
                      "success": success}, sort_keys=True))
    return 0 if success else 12


if __name__ == "__main__":
    raise SystemExit(main())
