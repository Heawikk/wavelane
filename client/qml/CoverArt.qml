import QtQuick
import Wavelane

/*!
    Album art with a quiet fallback.

    A missing cover is the normal case in a self-hosted library, so the
    placeholder is a muted tile whose hue comes from the title: lists stay
    distinguishable without a screen full of broken-image icons.
*/
Item {
    id: root

    property string coverPath: ""
    property string title: ""

    readonly property url source: coverPath ? api.coverUrl(coverPath) : ""

    readonly property int hashValue: {
        let hash = 0
        for (let i = 0; i < title.length; ++i)
            hash = ((hash << 5) - hash + title.charCodeAt(i)) | 0
        return Math.abs(hash)
    }

    Rectangle {
        anchors.fill: parent
        visible: cover.status !== Image.Ready
        color: Qt.hsla((root.hashValue % 360) / 360, 0.28, 0.2, 1.0)
        border.color: Theme.border
        border.width: 1

        Text {
            anchors.centerIn: parent
            text: root.title ? root.title.charAt(0).toUpperCase() : "♪"
            color: Qt.hsla((root.hashValue % 360) / 360, 0.35, 0.62, 1.0)
            font.family: Theme.sans
            font.pixelSize: Math.max(10, parent.width * 0.42)
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
