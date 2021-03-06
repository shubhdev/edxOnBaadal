# -*- coding: utf-8 -*-
""" Commerce app tests package. """
import datetime
import json

from django.conf import settings
from django.test import TestCase
from django.test.utils import override_settings
from freezegun import freeze_time
import httpretty
import jwt
import mock

from ecommerce_api_client import auth
from commerce import ecommerce_api_client
from student.tests.factories import UserFactory

JSON = 'application/json'
TEST_PUBLIC_URL_ROOT = 'http://www.example.com'
TEST_API_URL = 'http://www-internal.example.com/api'
TEST_API_SIGNING_KEY = 'edx'
TEST_BASKET_ID = 7
TEST_ORDER_NUMBER = '100004'
TEST_PAYMENT_DATA = {
    'payment_processor_name': 'test-processor',
    'payment_form_data': {},
    'payment_page_url': 'http://example.com/pay',
}


@override_settings(ECOMMERCE_API_SIGNING_KEY=TEST_API_SIGNING_KEY, ECOMMERCE_API_URL=TEST_API_URL)
class EcommerceApiClientTest(TestCase):
    """ Tests to ensure the client is initialized properly. """

    TEST_USER_EMAIL = 'test@example.com'
    TEST_CLIENT_ID = 'test-client-id'

    def setUp(self):
        super(EcommerceApiClientTest, self).setUp()

        self.user = UserFactory()
        self.user.email = self.TEST_USER_EMAIL
        self.user.save()  # pylint: disable=no-member

    @httpretty.activate
    @freeze_time('2015-7-2')
    @override_settings(JWT_ISSUER='http://example.com/oauth', JWT_EXPIRATION=30)
    def test_tracking_context(self):
        """
        Ensure the tracking context is set up in the api client correctly and
        automatically.
        """

        # fake an ecommerce api request.
        httpretty.register_uri(
            httpretty.POST,
            '{}/baskets/1/'.format(TEST_API_URL),
            status=200, body='{}',
            adding_headers={'Content-Type': JSON}
        )

        mock_tracker = mock.Mock()
        mock_tracker.resolve_context = mock.Mock(return_value={'client_id': self.TEST_CLIENT_ID})
        with mock.patch('commerce.tracker.get_tracker', return_value=mock_tracker):
            ecommerce_api_client(self.user).baskets(1).post()

        # make sure the request's JWT token payload included correct tracking context values.
        actual_header = httpretty.last_request().headers['Authorization']
        expected_payload = {
            'username': self.user.username,
            'full_name': self.user.profile.name,
            'email': self.user.email,
            'iss': settings.JWT_ISSUER,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=settings.JWT_EXPIRATION),
            'tracking_context': {
                'lms_user_id': self.user.id,  # pylint: disable=no-member
                'lms_client_id': self.TEST_CLIENT_ID,
            },
        }

        expected_header = 'JWT {}'.format(jwt.encode(expected_payload, TEST_API_SIGNING_KEY))
        self.assertEqual(actual_header, expected_header)

    @httpretty.activate
    def test_client_unicode(self):
        """
        The client should handle json responses properly when they contain
        unicode character data.

        Regression test for ECOM-1606.
        """
        expected_content = '{"result": "Préparatoire"}'
        httpretty.register_uri(
            httpretty.GET,
            '{}/baskets/1/order/'.format(TEST_API_URL),
            status=200, body=expected_content,
            adding_headers={'Content-Type': JSON},
        )
        actual_object = ecommerce_api_client(self.user).baskets(1).order.get()
        self.assertEqual(actual_object, {u"result": u"Préparatoire"})
