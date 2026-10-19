import QtQuick
import Wavelane

/*!
    The spectrum as a ring of short rays around the play button. Bass is at the
    top and the treble runs down both sides, so the ring is symmetric. The item
    has no size of its own: it is centred on its parent's origin.
*/
Item {
    id: root

    //! 32 values from low to high frequency, each 0..1.
    property var bands: []
    property color tint: Theme.text
    //! Distance from the centre to the inner end of the rays.
    property real innerRadius: 47
    property real maxLength: 20

    readonly property int rays: 64

    Repeater {
        model: root.rays

        delegate: Item {
            id: ray

            required property int index
            // 0..31 down the right side, then back up the left side
            readonly property int band: index < root.rays / 2 ? index : root.rays - 1 - index
            readonly property real value: root.bands && root.bands.length > band
                                          ? Math.max(0, Math.min(1, root.bands[band])) : 0

            rotation: index * 360 / root.rays

            Rectangle {
                width: 3
                height: 3 + ray.value * root.maxLength
                radius: 1.5
                x: -width / 2
                y: -root.innerRadius - height
                color: Qt.rgba(root.tint.r, root.tint.g, root.tint.b, 0.30 + 0.65 * ray.value)
            }
        }
    }
}
