from pathlib import Path

from ogdf_python import ogdf, cppinclude


def disown(obj):
    obj.__python_owns__ = False
    return obj


def call_layout(GA, L):
    print("Calling", type(L).__name__)
    L.call(GA)

    out = Path(__file__).parent / ("%s.svg" % type(L).__name__)
    print("Writing Drawing to", out)
    ogdf.GraphIO.drawSVG(GA, str(out))

    bb = GA.boundingBox()
    size = "%s x %s" % (bb.width(), bb.height())
    print("Drawing size:", size)
    assert bb.width() > 100, size
    assert bb.height() > 100, size


def test_layouts():
    cppinclude("ogdf/basic/graph_generators/randomized.h")
    cppinclude("ogdf/energybased/SpringEmbedderFRExact.h")
    cppinclude("ogdf/energybased/FMMMLayout.h")
    cppinclude("ogdf/layered/MedianHeuristic.h")
    cppinclude("ogdf/layered/OptimalHierarchyLayout.h")
    cppinclude("ogdf/layered/OptimalRanking.h")
    cppinclude("ogdf/layered/SugiyamaLayout.h")

    G = ogdf.Graph()
    ogdf.setSeed(1)
    ogdf.randomPlanarTriconnectedGraph(G, 20, 40)
    GA = ogdf.GraphAttributes(G, ogdf.GraphAttributes.all)

    for v in G.nodes:
        GA.width[v] = GA.height[v] = 20
        GA.label[v] = str(v.index())

    SL = ogdf.SugiyamaLayout()
    SL.setRanking(disown(ogdf.OptimalRanking()))
    SL.setCrossMin(disown(ogdf.MedianHeuristic()))
    ohl = disown(ogdf.OptimalHierarchyLayout())
    ohl.layerDistance(30.0)
    ohl.nodeDistance(40.0)
    ohl.weightBalancing(0.8)
    SL.setLayout(ohl)
    call_layout(GA, SL)

    for v in G.nodes:
        GA.x[v] /= 100  # SpringEmbedderFRExact needs some initial layout
        GA.y[v] /= 100

    sefr = ogdf.SpringEmbedderFRExact()
    sefr.idealEdgeLength(200.0)
    call_layout(GA, sefr)

    for v in G.nodes:
        GA.x[v] = GA.y[v] = 0

    fmmm = ogdf.FMMMLayout()
    fmmm.useHighLevelOptions(True)
    fmmm.unitEdgeLength(50.0)
    fmmm.newInitialPlacement(True)
    fmmm.qualityVersusSpeed(ogdf.FMMMOptions.QualityVsSpeed.GorgeousAndEfficient)
    call_layout(GA, fmmm)


if __name__ == "__main__":
    test_layouts()
