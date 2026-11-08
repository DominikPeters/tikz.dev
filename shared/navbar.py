"""Package menus in the tikz.dev header, shared by the builds of all manuals.

The pgf manual gets an "Other Packages" menu next to its title; the other
manuals get a menu on their title for switching between manuals. Links are
relative, so that a copy of the site below another path (tikz.dev/monorepo/)
links to itself.
"""

# The tikz.dev repository (issues, "About this HTML version")
REPO_URL = "https://github.com/DominikPeters/tikz.dev"
ISSUES_URL = REPO_URL + "/issues"

# package, name in the menu, folder below the site root
# (in the menu order: PGF/TikZ and PGFplots, then alphabetical)
PACKAGES = [
    ("pgf", 'PGF/<span class="tikzname">TikZ</span>', ""),
    ("pgfplots", "PGFplots", "pgfplots/"),
    ("chemfig", "chemfig", "chemfig/"),
    ("forest", "forest", "forest/"),
    ("nicematrix", "nicematrix", "nicematrix/"),
    ("pgf-pie", "pgf-pie", "pgf-pie/"),
    ("pgfgantt", "pgfgantt", "pgfgantt/"),
    ("tcolorbox", "tcolorbox", "tcolorbox/"),
    ("tikz-cd", "tikz-cd", "tikz-cd/"),
    ("tikz-feynman", "TikZ-Feynman", "tikz-feynman/"),
    ("tikzpingus", "TikZpingus", "tikzpingus/"),
    ("tkz-euclide", "tkz-euclide", "tkz-euclide/"),
    ("wheelchart", "wheelchart", "wheelchart/"),
]
FOLDERS = {pkg: folder for pkg, _, folder in PACKAGES}

# documentation on other sites, below a line at the end of the menus
EXTERNAL = [
    ("Beamer", "https://www.beamer.plus/home.html"),
    ("CircuiTikZ", "https://rmano.github.io/circuitikz/index.html"),
]
EXTERNAL_ICON = (
    '<svg class="pkg-menu-external" viewBox="0 0 24 24" role="img" aria-label="(external site)">'
    '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" '
    'fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
    'stroke-linejoin="round"/></svg>'
)

CARET = (
    '<svg class="pkg-menu-caret" viewBox="0 0 10 6" aria-hidden="true">'
    '<path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


def home_url(current, pkg):
    """URL of the start page of `pkg`, relative to a page of `current`."""
    if pkg == current:
        return "./"
    return "../" * FOLDERS[current].count("/") + FOLDERS[pkg] or "./"


def _items(current, skip_current, phone_links=()):
    items = []
    # links that are in the header on wider screens
    for name, href in phone_links:
        items.append(f'<li class="pkg-menu-phone"><a href="{href}">{name}</a></li>')
    if phone_links:
        items.append('<li class="pkg-menu-divider pkg-menu-phone" role="separator"></li>')
    for pkg, name, _ in PACKAGES:
        if pkg == current and skip_current:
            continue
        mark = ' aria-current="page"' if pkg == current else ""
        items.append(f'<li><a href="{home_url(current, pkg)}"{mark}>{name}</a></li>')
    items.append('<li class="pkg-menu-divider" role="separator"></li>')
    for name, href in EXTERNAL:
        items.append(f'<li><a href="{href}">{name}{EXTERNAL_ICON}</a></li>')
    return f'<ul class="pkg-menu-list">{"".join(items)}</ul>'


def other_packages_menu(current, phone_links=()):
    """'Other Packages' button with a menu of the other manuals. On phones,
    the button is only a caret and phone_links [(name, href)] join the menu."""
    return (
        '<span class="pkg-menu">'
        '<button type="button" class="pkg-menu-button" aria-expanded="false">'
        f'<span class="pkg-menu-label">Other Packages</span>{CARET}</button>'
        f"{_items(current, skip_current=True, phone_links=phone_links)}</span>"
    )


def title_menu(current, title):
    """Manual title (a link to its start page) with a menu of all manuals."""
    return (
        '<span class="pkg-menu">'
        f'<a href="{home_url(current, current)}">{title}</a>'
        '<button type="button" class="pkg-menu-button" aria-expanded="false" '
        f'aria-label="Other manuals">{CARET}</button>'
        f"{_items(current, skip_current=False)}</span>"
    )
