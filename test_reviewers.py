import unittest
from unittest.mock import Mock
import requests
from reviewers import reviewer_options, resolve_review_user_id
from single_payment_processor_recovered import SinglePaymentProcessor, ReviewerListError


class ReviewerTests(unittest.TestCase):
    def test_full_name_and_job(self):
        users = [{'jobNo': 'S80118', 'realName': '庄珊珊', 'userId': 'test-id'}]
        self.assertEqual(reviewer_options(users), [('S80118庄珊珊', 'test-id', 'S80118')])
        for selection in ('S80118', 'S80118庄珊珊'):
            self.assertEqual(resolve_review_user_id(users, selection), 'test-id')

    def test_label_value(self):
        users = {'data': [{'label': 'S80118庄珊珊', 'value': 'test-id'}]}
        self.assertEqual(resolve_review_user_id(users, 'S80118庄珊珊'), 'test-id')

    def test_no_ambiguous_match(self):
        users = [{'label': '同名', 'value': '1'}, {'label': '同名', 'value': '2'}]
        self.assertIsNone(resolve_review_user_id(users, '同名'))

    def test_http_failure_is_not_missing_person(self):
        processor = SinglePaymentProcessor()
        try:
            response = requests.Response()
            response.status_code = 405
            processor.session.get = Mock(return_value=response)
            with self.assertRaisesRegex(ReviewerListError, 'HTTP 405'):
                processor.get_review_user_list()
        finally:
            processor.session.close()
