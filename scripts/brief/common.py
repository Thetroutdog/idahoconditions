import re, html
PINE="#10241c"; GOLD="#e8c56b"; CREAM="#efece3"; MOSS="#2f6d4c"; INK="#1b2a23"
SERIF="Fraunces, Georgia, 'Times New Roman', serif"
SANS="Figtree, 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO="'IBM Plex Mono', Menlo, Consolas, 'Courier New', monospace"
FONTS=''  # no web-font link: email clients mostly ignore it, and the site no longer loads anything from Google. The stacks above fall back to Georgia/Helvetica/Menlo.
def md2html(s, link_color=MOSS):
    s = html.escape(s, quote=False)
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: f'<a href="{m.group(2)}" style="color:{link_color};text-decoration:underline;">{m.group(1)}</a>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'`([^`]+)`', lambda m: f'<span style="font-family:{MONO};font-size:13px;">{m.group(1)}</span>', s)
    s = s.replace('[CHECK', f'<span style="background:{GOLD};color:{PINE};font-family:{MONO};font-size:12px;padding:1px 4px;border-radius:3px;">[CHECK').replace('[EDITOR', f'<span style="background:{GOLD};color:{PINE};font-family:{MONO};font-size:12px;padding:1px 4px;border-radius:3px;">[EDITOR')
    # close spans for CHECK/EDITOR tags at the matching ']'
    out=[];i=0
    while True:
        j=s.find('border-radius:3px;">[',i)
        if j<0: out.append(s[i:]);break
        k=s.find(']',j+len('border-radius:3px;">['))
        out.append(s[i:k+1]+'</span>'); i=k+1
    return ''.join(out)
def p(s, size=16, color=INK, extra=''):
    return f'<p style="margin:0 0 14px;font-family:{SANS};font-size:{size}px;line-height:1.55;color:{color};{extra}">{md2html(s)}</p>'
def h2(s, color=PINE):
    return f'<h2 style="margin:26px 0 10px;font-family:{SERIF};font-weight:700;font-size:22px;line-height:1.25;color:{color};">{html.escape(s)}</h2>'
def page(title, preheader, body):
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>{FONTS}</head>
<body style="margin:0;padding:0;background:{PINE};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{html.escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PINE};"><tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:100%;background:{CREAM};border-radius:6px;overflow:hidden;">
{body}
</table></td></tr></table></body></html>'''
