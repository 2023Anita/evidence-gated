import unittest

from src.retry_config import validate_retry_count


class RetryConfigTest(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(validate_retry_count(3), 3)

    def test_zero(self):
        self.assertEqual(validate_retry_count(0), 0)

    def test_rejects_invalid_inputs(self):
        for value in (True, False, "3", 3.0, None):
            with self.subTest(value=value), self.assertRaises(TypeError):
                validate_retry_count(value)

    def test_rejects_negative(self):
        with self.assertRaises(ValueError):
            validate_retry_count(-1)
