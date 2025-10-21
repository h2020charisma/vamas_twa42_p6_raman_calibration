from utils import (
    load_config
)
import os.path
from pathlib import Path
from IPython.display import display, Markdown, HTML
import json


# + tags=["parameters"]
product = None
config_templates = None
config_root = None
keys = None
# -


_config = load_config(os.path.join(config_root, config_templates))

Path(os.path.dirname(product["nb"])).mkdir(parents=True, exist_ok=True)

templates = _config["templates"]

# --- Table of Contents ---
toc = "<h2>Table of Contents</h2><ul>"
for index, _entry in enumerate(templates.keys()):
    toc += f'<li><a href="#{_entry}">{index+1}. {_entry}</a></li>'
toc += "</ul>"

display(HTML(f'<div id="top">{toc}</div>'))

# --- Detailed Entries ---
for index, (_entry, data) in enumerate(templates.items()):
    display(HTML(f'<h2 id="{_entry}">{index+1}. {_entry}</h2>'))
    display(HTML(f"<p><b>Template:</b> {data.get('template','')}</p>"))
    display(HTML(f"<p><b>Path:</b> {data.get('path','')}</p>"))
    display(HTML(f"<p><b>Notes:</b> {data.get('notes','')}</p>"))
    
    # optional nested dicts
    for field in ["background", "units", "preprocess", "find_kw"]:
        if field in data:
            content = json.dumps(data[field], indent=2)
            display(HTML(f"<h4>{field.capitalize()}:</h4><pre>{content}</pre>"))
    
    # excluded columns
    excl = data.get("exclude_cols", [])
    if excl:
        excl_html = "<ul>" + "".join(f"<li>{c}</li>" for c in excl) + "</ul>"
        display(HTML("<h4>Excluded Columns:</h4>" + excl_html))
    
    display(HTML('<p><a href="#top">Back to top</a></p>'))
