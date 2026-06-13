"""
Render-Path Regression Tests for network_viz

These tests assert the contract that network_viz builders provide
to the rendering layer:
  - Each builder returns a pyvis.network.Network instance
  - generate_html() produces a string containing species names,
    physics solver markers, and (for flux) the Flux: tooltip marker
  - Special characters in species names (quotes, ampersands, angle
    brackets) round-trip without being silently dropped or
    double-escaped
  - Builders use cdn_resources=CDN_LOCAL so render_network's
    CDN_INLINE conditional override triggers (otherwise the iframe
    srcdoc would reference external JS that browsers block)
  - render_network itself returns an iframe Tag with srcdoc set
    (not src) and embeds the species names

They must pass both BEFORE and AFTER the pyvis.shiny.render_network
migration. The migration changes how the HTML is delivered to the
browser, not what generate_html() produces.

To run: pytest test_network_viz_render.py -v
"""

import pytest
import networkx as nx
import numpy as np
from pyvis.network import Network, CDN_LOCAL
from pyvis.shiny import render_network
from network_viz import create_topology_network, create_flux_network


@pytest.fixture
def simple_test_network():
    """Minimal 3-species food chain for render testing."""
    G = nx.DiGraph()
    G.add_nodes_from(['A', 'B', 'C'])
    G.add_edges_from([('A', 'B'), ('B', 'C')])
    species_names = ['Sprat', 'Herring', 'Cod']
    functional_groups = ['planktivore', 'planktivore', 'piscivore']
    biomass = np.array([100.0, 50.0, 25.0])
    colors = ['#1f77b4', '#1f77b4', '#ff7f0e']
    return G, species_names, functional_groups, biomass, colors


@pytest.fixture
def simple_flux_network(simple_test_network):
    """Same network plus a 3x3 flux matrix with non-zero edge fluxes."""
    G, species_names, functional_groups, biomass, colors = simple_test_network
    flux_matrix = np.array([
        [0.0, 10.0, 0.0],
        [0.0, 0.0, 5.0],
        [0.0, 0.0, 0.0],
    ])
    return G, species_names, functional_groups, biomass, colors, flux_matrix


def test_topology_builder_returns_pyvis_network(simple_test_network):
    G, species, groups, biomass, colors = simple_test_network
    net = create_topology_network(G, species, groups, biomass, colors)
    assert isinstance(net, Network), f"expected pyvis Network, got {type(net).__name__}"


def test_topology_html_contains_species_and_solver(simple_test_network):
    G, species, groups, biomass, colors = simple_test_network
    net = create_topology_network(G, species, groups, biomass, colors)
    html = net.generate_html()
    assert isinstance(html, str) and len(html) > 1000, "generate_html() returned empty or trivially small output"
    assert 'barnesHut' in html, "physics solver options not embedded in HTML"
    for name in species:
        assert name in html, f"species name {name!r} not present in rendered HTML"


def test_topology_tooltip_bold_marker_round_trips(simple_test_network):
    """The <b>...</b> wrapper around species names in tooltips must reach
    the browser as a tag, not as double-escaped &lt;b&gt; literal text.
    Catches a Jinja autoescape regression on the fork."""
    G, species, groups, biomass, colors = simple_test_network
    net = create_topology_network(G, species, groups, biomass, colors)
    html = net.generate_html()
    # <b>Sprat</b> must appear either raw or as JSON-escaped <
    # forms — but NOT as the double-escaped HTML &amp;lt;b&amp;gt;
    # which would render as literal text in the tooltip.
    assert '&amp;lt;b&amp;gt;' not in html, "tooltip bold markup got double-escaped — Jinja autoescape regression"


def test_topology_html_safe_for_special_chars():
    """Special characters in species names must round-trip — not just
    appear as substrings, but actually be present in valid escaped form
    and NOT double-escaped."""
    G = nx.DiGraph()
    G.add_nodes_from(['X', 'Y', 'Z'])
    G.add_edges_from([('X', 'Y'), ('Y', 'Z')])
    species = ['Salmo "trutta"', 'Mytilus & Co.', 'Genus <i>italicus</i>']
    groups = ['fish', 'shellfish', 'other']
    biomass = np.array([10.0, 5.0, 2.0])
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c']
    net = create_topology_network(G, species, groups, biomass, colors)
    html = net.generate_html()
    # The double-quote in 'Salmo "trutta"' must round-trip to a valid
    # encoded form: JSON-escaped \", HTML-entity &quot;, or JSON Unicode
    # escape " (pyvis uses HTML-safe JSON by default).
    assert '\\"trutta\\"' in html or '&quot;trutta&quot;' in html or '\\u0022trutta\\u0022' in html, \
        "double-quote in species name was dropped or wrongly escaped"
    # The literal & in 'Mytilus & Co.' must appear in some form: raw,
    # HTML entity &amp;, or JSON Unicode escape & (pyvis's default).
    assert 'Mytilus &amp; Co.' in html or 'Mytilus & Co.' in html or 'Mytilus \\u0026 Co.' in html, \
        "ampersand in species name was dropped"
    # The angle brackets in 'Genus <i>italicus</i>' must appear in some
    # escaped form (not silently stripped). Pyvis uses JSON Unicode
    # escapes (<, >) in HTML-safe mode.
    assert '&lt;i&gt;' in html or '<i>' in html or '\\u003ci\\u003eitalicus\\u003c/i\\u003e' in html, \
        "angle bracket in species name was dropped"
    # Most important: nothing got double-escaped to literal display.
    assert '&amp;amp;' not in html, "double-escaped ampersand"


def test_builders_use_cdn_local_so_render_network_inlines_assets(simple_test_network):
    """render_network's CDN_INLINE conditional override only triggers
    when the network was constructed with CDN_LOCAL (wrapper.py:260-264).
    If a future builder change switches to CDN_REMOTE, the iframe srcdoc
    will reference external JS that browsers may block — silently to a
    blank iframe with no Python exception. This test guards that
    assumption."""
    G, species, groups, biomass, colors = simple_test_network
    net = create_topology_network(G, species, groups, biomass, colors)
    assert net.cdn_resources == CDN_LOCAL, \
        f"builder changed cdn_resources to {net.cdn_resources!r} — render_network's CDN_INLINE branch is now skipped, iframe srcdoc will request external JS"


def test_flux_builder_returns_pyvis_network(simple_flux_network):
    G, species, groups, biomass, colors, flux_matrix = simple_flux_network
    net = create_flux_network(G, species, groups, biomass, colors, flux_matrix)
    assert isinstance(net, Network)


def test_flux_html_contains_species_and_flux_values(simple_flux_network):
    G, species, groups, biomass, colors, flux_matrix = simple_flux_network
    net = create_flux_network(G, species, groups, biomass, colors, flux_matrix)
    html = net.generate_html()
    assert isinstance(html, str) and len(html) > 1000
    assert 'barnesHut' in html
    for name in species:
        assert name in html
    # Edge tooltips reference "Flux:" string from network_viz.py
    assert 'Flux:' in html


def test_render_network_returns_iframe_with_srcdoc(simple_test_network):
    """render_network must produce an iframe Tag with srcdoc populated
    (not src), and the srcdoc must embed the species names. This is the
    only test that exercises the actual NEW code path the migration
    introduces — all earlier tests bypass render_network and call
    generate_html() directly."""
    G, species, groups, biomass, colors = simple_test_network
    net = create_topology_network(G, species, groups, biomass, colors)
    tag = render_network(net, height="600px", width="100%")
    assert tag.name == 'iframe', f"expected iframe Tag, got {tag.name!r}"
    assert 'srcdoc' in tag.attrs, "render_network must use srcdoc"
    assert 'src' not in tag.attrs, "render_network must NOT use src attribute"
    srcdoc = tag.attrs['srcdoc']
    assert len(srcdoc) > 1000, f"srcdoc trivially small: {len(srcdoc)} chars"
    for name in species:
        assert name in srcdoc, f"species {name!r} not in srcdoc"


def test_topology_node_size_and_y_position_pinned(viz_graph):
    """Pin node size (NODE_SIZE_MIN + biomass/max*SCALE) and TL->y normalization.
    biomass=[100,50,25], max=100, NODE_SIZE_MIN=4, NODE_SIZE_SCALE=25:
      sizes = 4 + [1.0,0.5,0.25]*25 = [29.0, 16.5, 10.25].
    TL=[1,2,3] -> y = 100*(tl-1)/(3-1) = [0, 50, 100]."""
    from network_viz import create_topology_network
    G, species, groups, biomass, colors = viz_graph
    net = create_topology_network(G, species, groups, biomass, colors)
    by_label = {n['label']: n for n in net.nodes}
    assert np.isclose(by_label['Sprat']['size'], 29.0)
    assert np.isclose(by_label['Herring']['size'], 16.5)
    assert np.isclose(by_label['Cod']['size'], 10.25)
    assert np.isclose(by_label['Sprat']['y'], 0.0)
    assert np.isclose(by_label['Herring']['y'], 50.0)
    assert np.isclose(by_label['Cod']['y'], 100.0)
