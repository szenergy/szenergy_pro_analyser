import logging
import unittest
from utils.logger import setup_logging, LOGGER_NAME
from main import parse_args


class TestLoggerAndCLI(unittest.TestCase):
    def test_parse_args_default(self):
        args = parse_args([])
        self.assertFalse(args.verbose)

    def test_parse_args_short_v(self):
        args = parse_args(["-v"])
        self.assertTrue(args.verbose)

    def test_parse_args_long_verbose(self):
        args = parse_args(["--verbose"])
        self.assertTrue(args.verbose)

    def test_setup_logging_non_verbose(self):
        logger = setup_logging(verbose=False)
        self.assertEqual(logging.getLogger().level, logging.WARNING)
        self.assertEqual(logger.name, LOGGER_NAME)

    def test_setup_logging_verbose(self):
        logger = setup_logging(verbose=True)
        self.assertEqual(logging.getLogger().level, logging.DEBUG)
        self.assertEqual(logger.name, LOGGER_NAME)


if __name__ == "__main__":
    unittest.main()
