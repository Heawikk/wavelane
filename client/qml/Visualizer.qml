import QtQuick
import QtQuick.Shapes
import Wavelane

/*!
    The strip of visualization under the wave's buttons, in a few styles.

    All of them read the same 32 frequency bands (bass first) and mirror them
    about the centre, so the loudest part sits under the play button and the
    treble fans out to both sides. With the style set to anything else (or "off")
    nothing is drawn at all.
*/
Item {
    id: root

    //! "bars", "wave" or "dots".
    property string style: "bars"
    //! 32 values from low to high frequency, each 0..1.
    property var bands: []
    property color tint: Theme.text

    readonly property int bandCount: 32
    readonly property int halfHeight: 34

    implicitWidth: 508
    implicitHeight: halfHeight * 2

    // The value of the band under horizontal position `u` (0 left .. 1 right),
    // interpolated between the two nearest bands so the curve has no steps.
    function valueAt(u) {
        const distance = Math.abs(u - 0.5) * 2 * (bandCount - 1)
        const low = Math.floor(distance)
        const high = Math.min(bandCount - 1, low + 1)
        const mix = distance - low
        const a = bands && bands.length > low ? bands[low] : 0
        const b = bands && bands.length > high ? bands[high] : 0
        return Math.max(0, Math.min(1, a + (b - a) * mix))
    }

    Loader {
        anchors.fill: parent
        sourceComponent: root.style === "bars" ? barsView
                         : root.style === "wave" ? waveView
                         : root.style === "dots" ? dotsView : null
    }

    Component {
        id: barsView
        Equalizer {
            anchors.centerIn: parent
            tint: root.tint
            bands: root.bands
        }
    }

    // A smooth, filled outline that swells with the sound, mirrored top and bottom.
    Component {
        id: waveView

        Shape {
            id: shape

            readonly property int samples: 120
            readonly property var outline: {
                const w = width
                const mid = height / 2
                const top = []
                const bottom = []
                for (let i = 0; i <= samples; ++i) {
                    const u = i / samples
                    const lift = 1 + root.valueAt(u) * (root.halfHeight - 1)
                    top.push(Qt.point(u * w, mid - lift))
                    bottom.push(Qt.point(u * w, mid + lift))
                }
                return top.concat(bottom.reverse())
            }

            preferredRendererType: Shape.CurveRenderer

            ShapePath {
                fillColor: Qt.rgba(root.tint.r, root.tint.g, root.tint.b, 0.32)
                strokeColor: Qt.rgba(root.tint.r, root.tint.g, root.tint.b, 0.95)
                strokeWidth: 2
                joinStyle: ShapePath.RoundJoin
                PathPolyline { path: shape.outline }
            }
        }
    }

    // A pair of beads per column that spread apart from the centre line as it gets louder.
    Component {
        id: dotsView

        Item {
            readonly property int columns: root.bandCount * 2
            readonly property real step: width / columns

            Repeater {
                model: parent.columns

                delegate: Item {
                    id: column

                    required property int index
                    readonly property real value: root.valueAt((index + 0.5) / parent.columns)
                    readonly property real size: 4 + value * 5

                    x: index * parent.step
                    width: parent.step
                    height: parent.height

                    Rectangle {
                        width: column.size
                        height: width
                        radius: width / 2
                        x: (column.width - width) / 2
                        y: column.height / 2 - column.value * (root.halfHeight - 3) - height / 2
                        color: Qt.rgba(root.tint.r, root.tint.g, root.tint.b, 0.35 + 0.6 * column.value)
                    }
                    Rectangle {
                        width: column.size
                        height: width
                        radius: width / 2
                        x: (column.width - width) / 2
                        y: column.height / 2 + column.value * (root.halfHeight - 3) - height / 2
                        color: Qt.rgba(root.tint.r, root.tint.g, root.tint.b, 0.35 + 0.6 * column.value)
                    }
                }
            }
        }
    }
}
