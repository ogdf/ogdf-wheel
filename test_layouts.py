from ogdf_python import ogdf, cppinclude

def disown(obj):
    obj.__python_owns__ = False
    return obj

def call_layout(GA, L):
    L.call(GA)
    ogdf.GraphIO.drawSVG(GA, "%s.svg" % type(L).__name__)
    bb = GA.boundingBox()
    assert bb.width() > 100, "%s x %s" % (bb.width(), bb.height())
    assert bb.height() > 100, "%s x %s" % (bb.width(), bb.height())

def test_layouts():
    cppinclude("ogdf/basic/graph_generators/randomized.h")
    cppinclude("ogdf/energybased/SpringEmbedderFRExact.h")
    cppinclude("ogdf/energybased/FMMMLayout.h")
    cppinclude("ogdf/layered/MedianHeuristic.h")
    cppinclude("ogdf/layered/OptimalHierarchyLayout.h")
    cppinclude("ogdf/layered/OptimalRanking.h")
    cppinclude("ogdf/layered/SugiyamaLayout.h")

    try:
        ogdf.GraphAttributes
    except:
        pass
    try:
        ogdf.Graph
    except:
        pass

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

    sefr = ogdf.SpringEmbedderFRExact()
    sefr.idealEdgeLength(200)
    call_layout(GA, sefr)

    fmmm = ogdf.FMMMLayout()
    fmmm.useHighLevelOptions(True)
    fmmm.unitEdgeLength(50.0)
    fmmm.newInitialPlacement(True)
    fmmm.qualityVersusSpeed(ogdf.FMMMOptions.QualityVsSpeed.GorgeousAndEfficient)
    call_layout(GA, fmmm)

if __name__ == "__main__":
    test_layouts()
