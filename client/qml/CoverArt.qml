import QtQuick
import Wavelane

/*!
    Album art with a graceful fallback.

    Most self-hosted libraries have patchy artwork, so a missing cover has to
    look deliberate rather than broken: the placeholder takes its colours from
    the title, which keeps rows in a list visually distinguishable.

    The artwork itself is drawn square. Rounding an Image in QML needs either
    Qt5Compat.GraphicalEffects or a hand-written shader, and neither is worth a
    dependency for a few pixels of corner.
*/
Item {
    id: root

    property string coverPath: ""
    property string title: ""
    property int radius: Theme.radiusSmall

    readonly property url source: coverPath ? api.coverUrl(coverPath) : ""

    // A stable pseudo-random hue per title, so the same album always gets the
    // same placeholder colour.
    readonly property int hashValue: {
        let hash = 0
        for (let i = 0; i < title.length; ++i)
            hash = ((hash << 5) - hash + title.charCodeAt(i)) | 0
        return Math.abs(hash)
    }

    Rectangle {
        anchors.fill: parent
        radius: root.radius
        visible: cover.status !== Image.Ready
        gradient: Gradient {
            GradientStop {
                position: 0.0
                color: Qt.hsla((root.hashValue % 360) / 360, 0.45, 0.32, 1.0)
            }
            GradientStop {
                position: 1.0
                color: Qt.hsla(((root.hashValue + 40) % 360) / 360, 0.45, 0.18, 1.0)
            }
        }

        Text {
            anchors.centerIn: parent
            text: root.title ? root.title.charAt(0).toUpperCase() : "♪"
            color: Qt.rgba(1, 1, 1, 0.75)
            font.pixelSize: Math.max(12, parent.width * 0.38)
            font.weight: Font.DemiBold
        }
    }

    Image {
        id: cover
        anchors.fill: parent
        source: root.source
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
        sourceSize.width: Math.max(64, Math.round(width * 2))
        visible: status === Image.Ready
    }
}
