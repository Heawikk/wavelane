import QtQuick
import Wavelane

/*!
    A mirrored row of thin bars, one per frequency band, growing from a centre
    line. Bass sits in the middle and the treble fans out to both sides, which
    reads as a waveform and keeps the loudest bars under the play button.
*/
Item {
    id: root

    //! 32 values from low to high frequency, each 0..1.
    property var bands: []
    property color tint: Theme.text
    property int barWidth: 4
    property int barGap: 4
    //! Height of one half (above or below the centre line).
    property int halfHeight: 34

    readonly property int bandCount: 32

    implicitWidth: bandCount * 2 * (barWidth + barGap) - barGap
    implicitHeight: halfHeight * 2

    Row {
        anchors.centerIn: parent
        spacing: root.barGap

        Repeater {
            model: root.bandCount * 2

            delegate: Item {
                id: bar

                required property int index
                // left half runs high-to-low into the centre, right half low-to-high
                readonly property int band: index < root.bandCount ? root.bandCount - 1 - index
                                                                   : index - root.bandCount
                readonly property real value: root.bands && root.bands.length > band
                                              ? Math.max(0, Math.min(1, root.bands[band])) : 0

                width: root.barWidth
                height: root.implicitHeight

                Rectangle {
                    anchors.centerIn: parent
                    width: parent.width
                    height: 2 + bar.value * (root.halfHeight * 2 - 2)
                    color: Qt.rgba(root.tint.r, root.tint.g, root.tint.b, 0.28 + 0.62 * bar.value)
                }
            }
        }
    }
}
