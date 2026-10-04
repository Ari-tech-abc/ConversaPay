import unittest
from backend.services.notification_templates import render_notification


class NotificationTemplateTests(unittest.TestCase):
    def test_payment_fields_escape_html_and_omit_private_customer_fields(self):
        subject, text, html = render_notification('payment_success', {'order_number': '<script>1</script>', 'total': '249.00', 'currency': 'ILS', 'customer_email': 'private@example.com', 'api_key': 'secret'}, 'https://example.com')
        self.assertIn('249.00 ILS', text)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>', html)
        self.assertNotIn('private@example.com', html)
        self.assertNotIn('secret', html)

    def test_security_message_does_not_include_credentials(self):
        _, text, html = render_notification('security_alerts', {'action': 'password_changed', 'password': 'secret'}, 'https://example.com')
        self.assertIn('הסיסמה שלך שונתה', text)
        self.assertNotIn('secret', html)

    def test_weekly_revenue_keeps_currencies_separate(self):
        _, text, _ = render_notification('weekly_digest', {'messages': 37, 'revenue_by_currency': {'ILS': '249', 'USD': '50'}}, 'https://example.com')
        self.assertIn('37', text)
        self.assertIn('249 ILS', text)
        self.assertIn('50 USD', text)

    def test_product_update_is_plain_text_and_subject_has_no_header_newlines(self):
        subject, text, html = render_notification('product_updates', {'title': 'Update\nInjected', 'body': '<img src=x onerror=alert(1)>'}, 'https://example.com')
        self.assertNotIn('\n', subject)
        self.assertNotIn('<img', html)
        self.assertIn('/settings#notification-settings', text)

    def test_unknown_category_is_rejected(self):
        with self.assertRaises(ValueError):
            render_notification('unknown', {}, 'https://example.com')


if __name__ == '__main__':
    unittest.main()
