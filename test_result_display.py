import unittest

from result_display import format_result


class ResultDisplayTests(unittest.TestCase):
    def result(self, state, error=None):
        return {"contract_no": "DEMO001", "submitted": [{}], "review": {
            "ids": ["1"], "response": {"code": 0, "data": [
                {"id": "1", "transStatus": state, "errorMsg": error}]}}}

    def test_business_failure_is_not_success(self):
        text = format_result(self.result("处理失败", "当前银行卡未签约"))
        self.assertEqual(text, "DEMO001｜处理失败：当前银行卡未签约")

    def test_confirmed(self):
        self.assertEqual(format_result(self.result("已复核")), "DEMO001｜复核成功")

    def test_unknown_is_not_success(self):
        self.assertIn("待确认", format_result(self.result(None)))

    def test_preview_has_no_personal_details(self):
        text = format_result({"contract_no": "DEMO001", "would_submit": [
            {"payAccountNo": "SECRET", "customerName": "PRIVATE"}]})
        self.assertIn("未复核", text)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("PRIVATE", text)

    def test_missing_review(self):
        self.assertIn("未完成复核", format_result({"submitted": [{}]}))

    def test_server_reason_stays_on_one_line(self):
        text = format_result(self.result("处理失败", "原因\n请核实"))
        self.assertNotIn("\n", text)


if __name__ == "__main__":
    unittest.main()
