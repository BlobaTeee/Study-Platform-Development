from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from .authentication import SupabaseJWTAuthentication


class SupabaseJWTAuthenticationTests(SimpleTestCase):
    def test_provides_authenticate_header(self):
        """DRF only returns 401 (not 403) for auth failures when the
        authenticator advertises a WWW-Authenticate scheme. Without this,
        an expired Supabase session surfaces as a confusing 403 that the
        frontend can't tell apart from the server being unreachable.
        """
        request = APIRequestFactory().get('/api/notebooks/notebooks/')
        header = SupabaseJWTAuthentication().authenticate_header(request)
        self.assertTrue(header, 'authenticate_header must be truthy so DRF returns 401')
        self.assertEqual(header.split()[0], 'Bearer')
