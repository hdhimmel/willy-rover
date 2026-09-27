import os, sys, email
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE', '1')

import config
from email_client import EmailClient

# FR-2000-013: "Verify inbound authentication results (SPF/DKIM/DMARC) before acting on any
# email; refuse to act on a message that did not pass DKIM regardless of its From header."
#
# Before this fix, _sender_allowed() (a plain string match against the From header) was the only
# gate email_client.py applied to inbound mail. That is a routing check, not authentication --
# any remote SMTP client can put whatever it likes in From. CLAUDE.md flags exactly this: "The
# real check is FR-2000-013 ... If you touch this path and that check is missing, it is a bug,
# not a simplification." There was no test file for email_client.py at all, so this also adds the
# first one.
#
# _dkim_authenticated() trusts the Authentication-Results header because it is stamped by the
# RECEIVING server (Gmail, for config.WILLIE_GOOGLE_ACCOUNT) as the message is accepted -- a
# remote sender forging the From line cannot also forge a passing verdict in a header their own
# message doesn't control.

def _msg(from_addr, auth_results=None):
    m = email.message.Message()
    m['From'] = from_addr
    m['Subject'] = 'test'
    if auth_results is not None:
        for v in (auth_results if isinstance(auth_results, list) else [auth_results]):
            m['Authentication-Results'] = v
    return m


def test_owner_mail_with_passing_dkim_is_authenticated():
    m = _msg(config.OWNER_EMAIL,
             'mx.google.com; dkim=pass header.i=@gmail.com header.s=20230601; spf=pass; dmarc=pass')
    assert EmailClient._dkim_authenticated(m) is True


def test_spoofed_from_header_with_no_authentication_results_is_refused():
    """The exact case FR-2000-013 exists for: a From header claiming the owner, no proof at all."""
    m = _msg(config.OWNER_EMAIL)
    assert EmailClient._dkim_authenticated(m) is False


def test_spoofed_from_header_with_failing_dkim_is_refused():
    m = _msg(config.OWNER_EMAIL,
             'mx.google.com; dkim=fail header.i=@example.com; spf=neutral; dmarc=fail')
    assert EmailClient._dkim_authenticated(m) is False


def test_dkim_none_is_refused():
    """A message with no DKIM signature at all (dkim=none) must not be treated as authenticated."""
    m = _msg(config.OWNER_EMAIL, 'mx.google.com; dkim=none; spf=pass; dmarc=none')
    assert EmailClient._dkim_authenticated(m) is False


def test_multiple_authentication_results_headers_any_passing_counts():
    """A forwarded/relayed message can carry more than one Authentication-Results header (one per
    hop) -- accept if any of them shows a passing DKIM verdict."""
    m = _msg(config.OWNER_EMAIL,
             ['relay.example.com; dkim=fail', 'mx.google.com; dkim=pass header.i=@gmail.com'])
    assert EmailClient._dkim_authenticated(m) is True


def test_dkim_pass_is_not_matched_as_a_loose_substring():
    """A malicious sender could try to smuggle the literal string past a naive check via an
    unrelated header value -- 'dkim=pass' must be a real token, not something that happens to
    appear inside a longer, unrelated word."""
    m = _msg(config.OWNER_EMAIL, 'mx.google.com; dkim=passfail; spf=pass')
    assert EmailClient._dkim_authenticated(m) is False
