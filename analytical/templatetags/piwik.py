"""
Piwik template tags and filters.
"""

from __future__ import absolute_import
import json

import re

from django.template import Library, Node, TemplateSyntaxError, Variable

from analytical.utils import is_internal_ip, disable_html, get_required_setting, get_user_from_context, get_identity


# domain name (characters separated by a dot), optional URI path, no slash
DOMAINPATH_RE = re.compile(r'^(([^./?#@:]+\.)+[^./?#@:]+)+(/[^/?#@:]+)*$')

# numeric ID
SITEID_RE = re.compile(r'^\d+$')

TRACKING_CODE = """
<script type="text/javascript">
  var _paq = _paq || [];
  %(pretrack)s
  _paq.push(%(method)s);
  _paq.push(['enableLinkTracking']);
  (function() {
    var u=(("https:" == document.location.protocol) ? "https" : "http") + "//%(url)s/";
    _paq.push(['setTrackerUrl', u+'piwik.php']);
    _paq.push(['setSiteId', %(siteid)s]);
    var d=document, g=d.createElement('script'), s=d.getElementsByTagName('script')[0]; g.type='text/javascript';
    g.defer=true; g.async=true; g.src=u+'piwik.js'; s.parentNode.insertBefore(g,s);
  })();
</script>
<noscript><p><img src="http://%(url)s/piwik.php?idsite=%(siteid)s" style="border:0;" alt="" /></p></noscript>
"""  # noqa


register = Library()


@register.tag
def piwik(parser, token):
    """
    Piwik tracking template tag.

    Renders Javascript code to track page visits.  You must supply
    your Piwik domain (plus optional URI path), and tracked site ID
    in the ``PIWIK_DOMAIN_PATH`` and the ``PIWIK_SITE_ID`` setting.
    """
    bits = token.split_contents()
    if len(bits) > 1:
        raise TemplateSyntaxError("'%s' takes no arguments" % bits[0])
    return PiwikNode()


class PiwikNode(Node):

    def __init__(self):
        self.domain_path = \
            get_required_setting('PIWIK_DOMAIN_PATH', DOMAINPATH_RE,
                                 "must be a domain name, optionally followed "
                                 "by an URI path, no trailing slash (e.g. "
                                 "piwik.example.com or my.piwik.server/path)")
        self.site_id = \
            get_required_setting('PIWIK_SITE_ID', SITEID_RE,
                                 "must be a (string containing a) number")

    def render(self, context):
        pretrack = _get_additional_calls(context)

        html = TRACKING_CODE % {
            'method': "['trackPageView']",
            'url': self.domain_path,
            'siteid': self.site_id,
            'pretrack': pretrack,
        }
        if is_internal_ip(context, 'PIWIK'):
            html = disable_html(html, 'Piwik')
        return html


def contribute_to_analytical(add_node):
    PiwikNode()  # ensure properly configured
    add_node('body_bottom', PiwikNode)


def _identify(user):
    return user.username


def _get_additional_calls(context):
    pretrack = ''

    vars = {}
    for dict_ in context:
        for var, val in dict_.items():
            if var.startswith('piwik_'):
                vars[var[6:]] = val

    if 'userid' not in vars:
        user = get_user_from_context(context)
        if user is not None and user.is_authenticated():
            userid = get_identity(context, 'piwik', _identify, user)
            pretrack += '_paq.push(["setUserId", "%s"]);\n' % userid
    else:
        pretrack += '_paq.push(["setUserId", "%s"]);\n' % vars['userid']
        del vars['userid']

    var_str = ''

    if 'document_title' in vars:
        var_str += '_paq.push(["setDocumentTitle", "%s"]);\n' % vars['document_title']
        del vars['document_title']

    for index, (raw_name, value) in enumerate(vars.items()):
        name, scope = raw_name.split('_')
        var_str += "_paq.push(['setCustomVariable', %(index)d, '%(name)s', '%(value)s', '%(scope)s']);\n" % {
            'index': index,
            'name': name,
            'value': value,
            'scope': scope,
        }

    pretrack = var_str + pretrack

    return pretrack


@register.simple_tag(takes_context=True)
def piwik_search(context, query, category=False, count=False):
    """
    Piwik search tracking template tag.

    Renders Javascript code to track internal page searches. See piwik tag.
    It takes 3 parameters:
      - Search string (required)
      - Search category (optional)
      - Result count (optional)
    """

    domain_path = \
        get_required_setting('PIWIK_DOMAIN_PATH', DOMAINPATH_RE,
                             "must be a domain name, optionally followed "
                             "by an URI path, no trailing slash (e.g. "
                             "piwik.example.com or my.piwik.server/path)")
    site_id = \
        get_required_setting('PIWIK_SITE_ID', SITEID_RE,
                             "must be a (string containing a) number")

    pretrack = _get_additional_calls(context)

    html = TRACKING_CODE % {
        'method': "['trackSiteSearch', %s, %s, %s]" % (
            json.dumps(query),
            json.dumps(category),
            json.dumps(count),
        ),
        'url': domain_path,
        'siteid': site_id,
        'pretrack': pretrack,
    }
    if is_internal_ip(context, 'PIWIK'):
        html = disable_html(html, 'Piwik')
    return html
