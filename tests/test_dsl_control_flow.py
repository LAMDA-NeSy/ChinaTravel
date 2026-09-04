import unittest

from chinatravel.symbol_verification.dsl import execute_dsl_code


class DslControlFlowTests(unittest.TestCase):
    def test_break_is_allowed_inside_loop(self):
        variables = {}
        execute_dsl_code(
            "result=True\n"
            "for value in [1, 2, 3]:\n"
            "  if value == 2:\n"
            "    result=False\n"
            "    break",
            variables,
        )
        self.assertFalse(variables["result"])

    def test_continue_is_allowed_inside_loop(self):
        variables = {}
        execute_dsl_code(
            "total=0\n"
            "for value in [1, 2, 3]:\n"
            "  if value == 2:\n"
            "    continue\n"
            "  total+=value\n"
            "result=(total==4)",
            variables,
        )
        self.assertTrue(variables["result"])


if __name__ == "__main__":
    unittest.main()
