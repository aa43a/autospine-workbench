"""Original code-drawn template, rendered once from the included SVG by Canvas.

This is generated candidate artwork, never a claimed character-source variant.
The packaged PNG avoids a Node/Canvas dependency during normal compilation.
"""
from base64 import b64decode

TEMPLATE_ID = 'procedural-mouth-interior-v1'
SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="48" viewBox="0 0 64 48">'
       '<defs><clipPath id="c"><ellipse cx="32" cy="24" rx="25" ry="18"/></clipPath></defs>'
       '<ellipse cx="32" cy="24" rx="25" ry="18" fill="#42212b"/>'
       '<g clip-path="url(#c)"><ellipse cx="33" cy="40" rx="21" ry="11" fill="#bd6879"/>'
       '<path d="M32 33 L32 39" stroke="#955064" stroke-width="1.2" stroke-linecap="round"/></g>'
       '<ellipse cx="32" cy="24" rx="25" ry="18" fill="none" stroke="#6c3d42" stroke-width="1.2"/></svg>')
PNG = b64decode(
    "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"
)
