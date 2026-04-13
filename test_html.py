import os
from gitsearch.template import get_html_template

html = get_html_template()
if "rawNodes.map" in html:
    print("Found map")
else:
    print("Not found map")
